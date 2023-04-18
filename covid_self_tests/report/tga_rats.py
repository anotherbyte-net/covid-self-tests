import csv
import dataclasses
import itertools
import json
import logging
import os
import pathlib
from datetime import timezone, datetime

from covid_self_tests.report import pdf_table, models

logger = logging.getLogger(__name__)


class Report:
    _keys_details_items = {
        "url",
        "data-group",
        "Australian sponsor",
        "ARTG",
        "Manufacturer",
        "Date approved for supply",
        "Type of test",
        "Intended use",
        "Model/Type of use",
        "files",
    }
    _keys_details_pages = {"data-group", "date", "title", "url", "summary", "files"}
    _keys_sensitivity = {
        "data-group",
        "Name of self-test* and how to use the test",
        "urls",
        "Sample type used",
        "Australian Sponsor (supplier)",
        "Manufacturer",
        "ARTG",
        "Clinical Sensitivity",
        "Date Approved",
        "Shelf Life",
        "files",
    }

    def __init__(self):
        self._data_dir = pathlib.Path(os.environ.get("OUTPUT_DIR"))
        self._files_dir = self._data_dir / "filestore" / "full"
        self._pdf_table_doc = pdf_table.PdfTableDocument()
        self._outcome_dir = self._data_dir / "outcomes"

        self._outcome_dir.mkdir(exist_ok=True, parents=True)

    def run(self):
        csv_data = self.read_csv_files()
        pdf_data = self.read_pdf_text_files()

        most_recent = self._most_recent_data(csv_data, pdf_data)
        combined_data = self._combine_data(most_recent)

        data = sorted([(k, v) for k, v in combined_data.items()])

        now = datetime.now(timezone.utc)
        outcome_path = (
            self._outcome_dir
            / f"{now.isoformat(timespec='seconds').replace(':', '-')}-outcomes.csv"
        )
        field_names = [i.name for i in dataclasses.fields(models.RatInfo)]
        with open(outcome_path, "wt", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, field_names)
            writer.writeheader()

            for match, info in data:
                item = models.RatInfo(
                    artg=match.artg,
                    title=match.title,
                    details_url=info.details_url,
                    sponsor=info.sponsor,
                    date_approved=info.date_approved,
                    manufacturer=info.manufacturer,
                    test_type=info.test_type,
                    intended_use=info.intended_use,
                    date_updated=info.date_updated,
                    type_of_use=info.type_of_use,
                    instructions_url=info.instructions_url,
                    sample_type=info.sample_type,
                    sensitivity=info.sensitivity,
                    expiry=info.expiry,
                    comment=info.comment,
                    variants=info.variants,
                    review_wild=info.review_wild,
                    review_delta=info.review_delta,
                    review_omicron=info.review_omicron,
                    review_quality=info.review_quality,
                    errors=str(info.errors) if info.errors else "",
                )
                writer.writerow(dataclasses.asdict(item))

        return data

    def read_pdf_text_files(self):
        data = {}
        for entry in self._files_dir.iterdir():
            if not entry.is_file() or entry.suffix not in [".pdf", ".txt"]:
                continue

            key = entry.stem.split("-")[0]
            if key not in data:
                data[key] = {}

            data[key][entry.suffix.strip(".")] = entry

            if entry.suffix == ".txt":
                data[key]["data"] = self._pdf_table_doc.read(entry)
        return data

    def read_csv_files(self):
        csv_data = {}
        for entry in self._data_dir.iterdir():
            if not entry.is_file() or not entry.suffix == ".csv":
                continue

            csv_data[entry] = []
            with open(entry, "rt", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    csv_data[entry].append(row)

        return csv_data

    def _most_recent_data(self, csv_data, pdf_data):
        # get only the most recent data
        csv_sorted = sorted(
            [(*k.stem.split("-tga-rats-"), v) for k, v in csv_data.items()]
        )
        csv_grouped = [
            (k, list(g)) for k, g in itertools.groupby(csv_sorted, key=lambda x: x[0])
        ]
        csv_recent = {name: data for date, name, data in csv_grouped[-1][1]}

        csv_review = sorted(
            [
                (
                    i.get("file_urls"),
                    json.loads(i.get("files").replace("'", '"'))[0]["path"],
                )
                for i in csv_recent["review"]
            ]
        )
        csv_review_pdf_key = pathlib.Path(csv_review[-1][1]).stem
        pdf_recent = pdf_data[csv_review_pdf_key]["data"]

        raw_data = {
            "details-items": csv_recent["details-items"],
            "details-pages": csv_recent["details-pages"],
            "sensitivity": csv_recent["sensitivity"],
            "review": pdf_recent,
        }
        return raw_data

    def _combine_data(self, data: dict):
        result: dict[models.ProductMatchInfo, models.ProductInfo] = {}

        # create a mapping between the url and the detail page info
        details_pages_urls = {i.get("url"): i for i in data["details-pages"]}

        # details items and pages
        for item in data["details-items"]:
            raw_artg = item.get("ARTG")
            url = item.get("url")
            date_approved = item.get("Date approved for supply")
            manufacturer = item.get("Manufacturer")
            test_type = item.get("Type of test")
            sponsor = item.get("Australian sponsor")
            intended_use = item.get("Intended use")
            type_of_use = item.get("Model/Type of use")

            artg = raw_artg.split("(")[-1].strip(" )")
            # tga_title = raw_artg.replace(sponsor, "").replace(artg, "").strip(" ()-")

            details_page_item = details_pages_urls.get(url)
            date_updated = details_page_item.get("date")
            product_name = details_page_item.get("title")
            # details_page_summary = details_page_item.get("summary")

            info = models.ProductMatchInfo.from_raw(product_name, artg, intended_use)

            if not info.is_self_test:
                continue

            # build item data
            product = models.ProductInfo(
                details_url=url,
                sponsor=sponsor,
                date_approved=date_approved,
                manufacturer=manufacturer,
                test_type=test_type,
                intended_use=intended_use,
                date_updated=date_updated,
                type_of_use=type_of_use,
            )

            # populate the result structure
            if info in result:
                raise ValueError([result[info], info])

            result[info] = product

            # keys check
            keys_mapping = [
                (set(item.keys()), self._keys_details_items),
                (set(details_page_item.keys()), self._keys_details_pages),
            ]
            self._check_keys(keys_mapping)

        # sensitivity items
        # add the sensitivity properties to the existing properties
        for item in data["sensitivity"]:
            artg = item.get("ARTG")
            url = item.get("urls")
            sample_type = item.get("Sample type used")
            sponsor = item.get("Australian Sponsor (supplier)")
            manufacturer = item.get("Manufacturer")
            sensitivity = item.get("Clinical Sensitivity")
            date_approved = item.get("Date Approved")
            expiry = item.get("Shelf Life")
            name_and_use = item.get("Name of self-test* and how to use the test")

            info = models.ProductMatchInfo.from_raw(name_and_use, artg)

            if not info.is_self_test:
                continue

            if info not in result:
                result[info] = models.ProductInfo()

            result[info].set_prop("instructions_url", url)
            result[info].set_prop("sample_type", sample_type)
            result[info].set_prop("sponsor", sponsor)
            result[info].set_prop("manufacturer", manufacturer)
            result[info].set_prop("sensitivity", sensitivity)
            result[info].set_prop("date_approved", date_approved)
            result[info].set_prop("expiry", expiry)

            # keys check
            keys_mapping = [(set(item.keys()), self._keys_sensitivity)]
            self._check_keys(keys_mapping)

        for item in data["review"].entries:
            artg = item.artg
            comment = item.comment
            manufacturer = item.manufacturer
            sponsor = item.sponsor
            evidence = sorted({i.name.strip(" *") for i in item.manufacturer_evidence})
            product_names = item.product_names
            batches = item.batches

            review_result = self._eval_review_batches(batches)

            # try to add each product_name
            # select the latest batch (by batch number) (previous tests aren't so useful)

            for product_name in product_names:
                info = models.ProductMatchInfo.from_raw(product_name, artg)

                if not info.is_self_test:
                    continue

                if info not in result:
                    result[info] = models.ProductInfo()

                result[info].set_prop("comment", comment)
                result[info].set_prop("sponsor", sponsor)
                result[info].set_prop("manufacturer", manufacturer)
                result[info].set_prop("variants", ",".join(evidence))
                result[info].set_prop("review_wild", review_result.get("wild"))
                result[info].set_prop("review_delta", review_result.get("delta"))
                result[info].set_prop("review_omicron", review_result.get("omicron"))
                result[info].set_prop("review_quality", review_result.get("quality"))

        return result

    def _check_keys(self, keys: list[tuple[set, set]]) -> None:
        for actual, expected in keys:
            extra_keys = actual - expected
            if extra_keys:
                raise ValueError(extra_keys)

    def _eval_review_batches(self, batches) -> dict:
        if not batches:
            return {}

        # assume the last batch code is the most recent
        batches_sorted = sorted(batches, key=lambda x: x.batch)
        batch = batches_sorted[-1]

        if len(batches) > 1:
            previous_all_bad = all([not batch.all_compliant for batch in batches[0:-1]])
            previous_all_good = all([batch.all_compliant for batch in batches[0:-1]])
            if not previous_all_bad and not previous_all_good:
                raise ValueError()

        result = {}
        for i in batch.analytical_sensitivities:
            if i.compliant:
                result[i.name] = "yes"
            elif i.comment:
                result[i.name] = "no"
            elif not i.compliant:
                result[i.name] = "no"
            else:
                raise ValueError()

        return result


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        level=logging.INFO,
    )
    Report().run()
