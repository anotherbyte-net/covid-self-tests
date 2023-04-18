import pathlib
import re
import typing
from datetime import datetime

import chardet as chardet

from covid_self_tests.report import models


class PdfTableDocument:
    _key_lines = {
        "yes": "Compliant with the WHO guidelines "
        "(LOD within range 100-1000 TCID50/mL) during TGA validation",
        "no": "Non-compliant with the WHO guidelines "
        "(LOD does not fall within the range 100-1000 TCID50/mL) during TGA validation",
        "multiple-products": "Where multiple RATs are included under the one (1) ARTG number "
        "and have the same product composition, they have",
        "tests-protein-studies": "In manufacturer provided evidence, "
        "variants that have only been tested with recombinant protein studies.",
    }

    def read(self, file_path: pathlib.Path) -> models.RatReviewTable:
        with open(file_path, "rb") as f:
            raw = f.read()

        result_date_pattern = re.compile(
            r"^Results\s+as\s+at\s+(?P<date>\d+\s+\S+\s+\d+).*?http.*$"
        )
        page_of_pattern = re.compile(r"^Page\s+\d+\s+of\s+\d+$")

        indicators = {}
        headers = {}
        data = []

        encoding_detected = chardet.detect(raw)
        encoding = encoding_detected.get("encoding")
        text = raw.decode(encoding)
        pages = text.split("\f")
        result_date = None
        for page_index, page in enumerate(pages):
            headers[page_index] = PdfTableHeader()
            lines = page.splitlines()

            for line in lines:
                if not line or not line.strip():
                    continue

                result_date_match = result_date_pattern.fullmatch(line.strip())
                if result_date_match:
                    if not result_date:
                        result_date = datetime.strptime(
                            result_date_match.group("date"), "%d %B %Y"
                        )
                    continue

                page_of_match = page_of_pattern.fullmatch(line.strip())
                if page_of_match:
                    continue

                indicators_raw = self._key_indicator(line)
                if indicators_raw:
                    indicators[indicators_raw[0]] = indicators_raw[1]
                    continue

                is_header = headers[page_index].add_header_line(line)
                if is_header:
                    continue

                if not headers[page_index].is_complete:
                    continue

                item = headers[page_index].get_row(line)
                item["page"] = page_index + 1

                data.append(item)

        convert = PdfTableToRatReviewEntries()
        entries = convert.build(data, indicators)

        result = models.RatReviewTable(date=result_date, entries=entries)
        return result

    def _key_indicator(self, line: str) -> typing.Optional[tuple[str, str]]:
        for key, value in self._key_lines.items():
            if value in line:
                return key, line[0]
        return None


class PdfTableHeader:
    _raw_columns = [
        {"name": "artg", "columns": ["ARTG"], "align": "left"},
        {"name": "sponsor", "columns": ["Sponsor"], "align": "left"},
        {"name": "manufacturer", "columns": ["Manufacturer"], "align": "left"},
        {"name": "name", "columns": ["Test Kit name"], "align": "left"},
        {
            "name": "batch",
            "columns": ["TGA testing", "", "Batch number"],
            "align": "middle",
        },
        {
            "name": "wild",
            "columns": ["TGA", "testing", "", "Wild type", "analytical", "sensitivity"],
            "align": "middle",
        },
        {
            "name": "delta",
            "columns": ["TGA", "testing", "", "Delta", "analytical", "sensitivity"],
            "align": "middle",
        },
        {
            "name": "omicron",
            "columns": ["TGA", "testing", "", "Omicron", "analytical", "sensitivity"],
            "align": "middle",
        },
        {
            "name": "quality",
            "columns": ["TGA", "testing", "", "Device", "quality"],
            "align": "middle",
        },
        {
            "name": "provided",
            "columns": ["Manufacturer", "provided evidence"],
            "align": "left",
        },
    ]
    _col_sep = "  "

    def __init__(self):
        self._pdf_header_lines = []
        self._pdf_header_cols = len(self._raw_columns)
        self._pdf_header_rows = max([len(h.get("columns")) for h in self._raw_columns])

        self._build()

        self._actual: dict[int, list[dict[str, int]]] = {}

    @property
    def is_complete(self):
        return len(self._actual) == self._pdf_header_rows

    @property
    def header_indexes(self) -> dict[int, dict]:
        initial = {}
        for line_index, line_headers in self._actual.items():
            for header in line_headers:
                header_index = header.get("item")
                start_index = header.get("start_index")
                end_index = header.get("end_index")
                name = self._raw_columns[header_index].get("name")

                value = {"name": name, "start": start_index, "end": end_index}

                if header_index not in initial:
                    initial[header_index] = value
                    continue

                if start_index <= initial[header_index]["start"]:
                    initial[header_index]["start"] = start_index
                if end_index >= initial[header_index]["end"]:
                    initial[header_index]["end"] = end_index

        header_count = len(self._raw_columns)
        col_sep = self._col_sep
        col_sep_len = len(col_sep)

        result = {}
        for index, header in initial.items():
            name = header.get("name")
            start_index = header.get("start")
            end_index = header.get("end")
            align = self._raw_columns[index].get("align")

            # get the next and previous items
            # to build the start and end index for the column
            if (index + 1) < header_count:
                next_index = index + 1
                next_item = initial[next_index]
                next_start = next_item.get("start")
                next_end = next_item.get("end")
                next_align = self._raw_columns[next_index].get("align")
                right_diff = next_start - end_index
            else:
                next_start = -1
                next_end = None
                next_align = None
                end_index = -1
                right_diff = None

            if index > 0:
                prev_index = index - 1
                prev_item = initial[prev_index]
                prev_start = prev_item.get("start")
                prev_end = prev_item.get("end")
                left_diff = start_index - prev_end
            else:
                prev_start = None
                prev_end = 0
                start_index = 0
                left_diff = None

            # get the diffs for the prev x2 and next x2
            if (index + 2) < header_count:
                next_2_index = index + 2
                next_2_item = initial[next_2_index]
                next_right_diff = next_2_item.get("start") - next_end
            else:
                next_right_diff = None

            if index > 1:
                prev_2_index = index - 2
                prev_2_item = initial[prev_2_index]
                prev_left_diff = prev_start - prev_2_item.get("end")
            else:
                prev_left_diff = None

            info = (
                f"){prev_left_diff}[{prev_start}-{prev_end}]{left_diff}"
                f"<{start_index}-{end_index}>"
                f"{right_diff}[{next_start}-{next_end}]{next_right_diff}("
            )

            # use the next column's start index, minus col sep length
            if next_align == "left":
                end_index = next_start - col_sep_len

            # set the result header
            result[index] = {
                "name": name,
                "start": int(start_index),
                "end": int(end_index),
                "info": info,
                "align": align,
            }
            if start_index < 0 or (start_index >= end_index >= 0):
                raise ValueError(result[index])

        return result

    def add_header_line(self, line: str) -> bool:
        if self.is_complete:
            return False

        current_index = 0
        result = []
        for headers_index, headers in enumerate(self._pdf_header_lines):
            for header_index, header in enumerate(headers):
                if header not in line[current_index:]:
                    # if one of the headers is not in the line,
                    # restart the header detection with the next set of headers
                    result = []
                    break
                if header:
                    # get the start and end indexes of the column
                    start_index = line.index(header, current_index)
                    end_index = start_index + len(header)
                    current_index = end_index
                    result.append(
                        {
                            "header": header,
                            "start_index": start_index,
                            "end_index": end_index,
                            "item": header_index,
                        }
                    )
            if result:
                self._actual[headers_index] = result
                return True
        if not result:
            return False
        else:
            raise ValueError()

    def get_row(self, line: str) -> typing.Optional[dict]:
        data = self.header_indexes
        col_count = self._pdf_header_cols
        col_sep = self._col_sep
        col_sep_len = len(self._col_sep)

        result = {}
        for index in data:
            item = data[index]

            name = item.get("name")
            start_index = item.get("start")
            end_index = item.get("end")
            align = item.get("align")

            value = line[start_index:end_index]

            if align == "left" and index > 0:
                confirm_start = start_index - col_sep_len
                confirm_end = start_index
                confirm_value = line[confirm_start:confirm_end]
                confirm = not confirm_value.strip() or confirm_value == col_sep
                if not confirm:
                    raise ValueError(item)

            if name == "quality":
                # fix: expand the extracted text to try to get the value
                value_start = start_index - 3
                value_end = end_index
                value = line[value_start:value_end]

            if value and not value[-1].isspace():
                # see if the value should include more text to the right
                extra = 0
                while True:
                    extra_start = end_index + (col_sep_len * extra)
                    extra_end = end_index + (col_sep_len * (extra + 1))
                    extra_value = line[extra_start:extra_end]
                    if not extra_value.strip():
                        break
                    value += extra_value
                    extra += 1

            if (index + 1) == col_count:
                value = line[start_index:]

            result[name] = value

        return result

    def _build(self):
        for col in range(self._pdf_header_rows):
            self._pdf_header_lines.append([])
            for row in range(self._pdf_header_cols):
                row_data = self._raw_columns[row]
                row_val = row_data.get("columns")
                if len(row_val) > col:
                    col_val = row_val[col]
                    value = col_val
                else:
                    value = ""
                self._pdf_header_lines[col].append(value)


class PdfTableToRatReviewEntries:
    def build(self, data: list[dict], indicators: dict) -> list[models.RatReviewEntry]:
        entries = []

        current_entry = {}
        current_names = []
        current_batches = []
        current_evidence = []

        multi_product_indicator = indicators["multiple-products"]

        for item in data:
            artg = self._norm(item.get("artg"))
            sponsor = self._norm(item.get("sponsor"))
            manufacturer = self._norm(item.get("manufacturer"))
            is_new_name, name = self._norm_name(
                item.get("name"), multi_product_indicator
            )
            batch = self._norm(item.get("batch"))
            wild = self._norm(item.get("wild"))
            delta = self._norm(item.get("delta"))
            omicron = self._norm(item.get("omicron"))
            quality = self._norm(item.get("quality"))
            provided = self._norm(item.get("provided"))

            if artg and not all(c.isdigit() for c in artg):
                artg_comment = artg
                artg = None
            else:
                artg_comment = None

            if artg and current_entry:
                # store the current entry
                entries.append(
                    self._build_entry(
                        current_entry,
                        current_names,
                        current_batches,
                        current_evidence,
                        indicators,
                    )
                )

                # reset
                current_entry = {}
                current_names = []
                current_batches = []
                current_evidence = []

            if artg:
                # move on to the next entry
                current_entry = {}

            if not name or not current_names or is_new_name:
                # move on to the next product name
                current_names.append("")

            if batch:
                # move on to the next batch
                current_batches.append({})

            if not provided or not current_evidence or ":" in provided:
                # move on to the next group of manufacturer evidence
                current_evidence.append("")

            self._dict_add(current_entry, "artg", artg)
            self._dict_add(current_entry, "sponsor", sponsor)
            self._dict_add(current_entry, "manufacturer", manufacturer)
            self._dict_add(current_entry, "artg_comment", artg_comment)

            self._list_add(current_names, name)

            self._dict_add(current_batches[-1], "batch", batch)
            self._dict_add(current_batches[-1], "wild", wild)
            self._dict_add(current_batches[-1], "delta", delta)
            self._dict_add(current_batches[-1], "omicron", omicron)
            self._dict_add(current_batches[-1], "quality", quality)

            self._list_add(current_evidence, provided)

        return entries

    def _norm(self, value: str) -> typing.Optional[typing.Union[str, bool]]:
        pattern = re.compile(r"\s+")
        with_spaces = pattern.sub(" ", value)
        result = with_spaces.strip()

        if result == "yes":
            return True
        if result == "no":
            return False

        if not result:
            return None

        return result

    def _norm_name(self, value: str, multiple_name_indicator: str):
        pattern = re.compile(r"\s+")
        with_spaces = pattern.sub(" ", value)
        result = with_spaces.strip()

        if result and with_spaces and with_spaces.startswith(multiple_name_indicator):
            return True, result

        if not result:
            return False, None

        return False, result

    def _dict_add(self, container: dict, key: str, value: typing.Any) -> None:
        if key not in container:
            container[key] = ""
        container[key] += " " + str(value) if value is not None else ""
        container[key] = container[key].strip()

    def _list_add(self, container: list, value: str) -> None:
        container[-1] = container[-1] + " " + (value or "")
        container[-1] = container[-1].strip()

    def _build_entry(
        self, entry: dict, names: list, batches: list, evidence: list, indicators: dict
    ):
        # build the manufacturer evidence
        manufacturer_evidence = []
        current_group = None
        for item in evidence:
            if not item:
                continue

            colon_count = item.count(":")
            if colon_count == 1:
                group, values = item.split(":")
                current_group = group
            elif colon_count > 1:
                raise ValueError(f"{entry}: {item}")
            else:
                group = current_group
                values = item

            for value in values.split(","):
                manufacturer_evidence.append(
                    models.RatReviewManufacturerEvidence(group, value)
                )

        # build the review batch information
        batch_items = []
        indicator_review_yes = indicators["yes"]
        indicator_review_no = indicators["no"]
        for item in batches:
            batch = item.get("batch")
            tests = []
            for key, value in item.items():
                if key == "batch":
                    continue
                if value == indicator_review_yes:
                    compliant = True
                    comment = None
                elif value == indicator_review_no:
                    compliant = False
                    comment = None
                else:
                    compliant = False
                    comment = value
                tests.append(
                    models.RatReviewAnalyticalSensitivity(
                        name=key, compliant=compliant, comment=comment
                    )
                )
            batch_items.append(
                models.RatReviewBatch(batch=batch, analytical_sensitivities=tests)
            )

        # build the product names
        product_names = []
        for name in names:
            if not name:
                continue
            if name and name.strip():
                product_names.append(name)

        entry = models.RatReviewEntry(
            artg=entry.get("artg"),
            comment=entry.get("artg_comment"),
            sponsor=entry.get("sponsor"),
            manufacturer=entry.get("manufacturer"),
            product_names=product_names,
            batches=batch_items,
            manufacturer_evidence=manufacturer_evidence,
        )
        return entry
