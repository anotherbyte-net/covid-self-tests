import dataclasses
import re
import typing
import unicodedata
from datetime import datetime

from covid_self_tests.report.tga_rats import logger


@dataclasses.dataclass
class RatReviewManufacturerEvidence:
    group: str
    name: str


@dataclasses.dataclass
class RatReviewAnalyticalSensitivity:
    name: str
    compliant: bool
    comment: str


@dataclasses.dataclass
class RatReviewBatch:
    batch: str
    analytical_sensitivities: list[RatReviewAnalyticalSensitivity]

    @property
    def all_compliant(self):
        for i in self.analytical_sensitivities:
            if not i.compliant:
                return False
        return True


@dataclasses.dataclass
class RatReviewEntry:
    artg: str
    comment: str
    sponsor: str
    manufacturer: str
    product_names: list[str]
    batches: list[RatReviewBatch]
    manufacturer_evidence: list[RatReviewManufacturerEvidence]


@dataclasses.dataclass
class RatReviewTable:
    date: datetime
    entries: list[RatReviewEntry]


@dataclasses.dataclass(eq=True, frozen=True, order=True)
class ProductMatchInfo:
    artg: str
    """The TGA identifier."""
    title: str = dataclasses.field(compare=False, hash=False)
    """The normalised name for display."""
    name: str = dataclasses.field(compare=False, hash=False)
    """The original name."""
    slug: str
    """The normalised name for comparisons."""
    is_poct: bool
    """Is this a point of care test?"""
    is_self: bool
    """Is this a self / home test?"""
    is_lab: bool
    """Is this a laboratory test?"""

    def __str__(self) -> str:
        if self.is_self:
            test_type = "self"
        elif self.is_poct:
            test_type = "poct"
        elif self.is_lab:
            test_type = "lab"
        else:
            test_type = "unknown"
        return f"{self.artg} [{test_type}] {self.title}"

    @property
    def is_self_test(self):
        return self.is_self and not self.is_lab and not self.is_poct

    @classmethod
    def from_raw(
        cls,
        name: str,
        artg: typing.Optional[str] = None,
        intended_use: typing.Optional[str] = None,
    ) -> "ProductMatchInfo":
        replacements = [("pdf,", "pdf "), ("PDF,", "pdf "), (")(", ") (")]
        new_name = name
        for find, replace in replacements:
            new_name = new_name.replace(find, replace)

        pdf_pattern = re.compile(r"\(pdf.*?\)")
        pdf_match = pdf_pattern.search(new_name)
        if pdf_match:
            new_name_0 = 0
            new_name_1 = pdf_match.start()
            new_name_2 = pdf_match.end()
            new_name = new_name[new_name_0:new_name_1] + new_name[new_name_2:]

        slug = cls._slugify(new_name)
        split = slug.split("-")

        # is this a point of care tests (POCT)?
        is_poct = (
            any(w in split for w in ["poct"])
            or intended_use
            in [
                "Laboratory/Point-of-care test",
                "Point-of-care test",
            ]
            or "point-of-care" in slug
        )

        # is this a self test?
        # intended_use == "" is an empty value, assume self test
        is_self = (
            any(w in split for w in ["self", "selftest", "home"])
            or intended_use in ["Self-test", ""]
            or "self-test" in slug
        )

        # is this a lab test?
        is_lab = any(w in split for w in ["laboratory", "lab"]) or intended_use in [
            "Laboratory",
            "Laboratory/Point-of-care test",
        ]

        if not is_poct and not is_self and not is_lab:
            logger.warning("No information on intended use. Assuming self test.")
            is_self = True

        if is_self and (is_poct or is_lab):
            logger.warning("Unexpected test type combination.")
            is_self = False

        # remove the pdf details
        if "pdf" in split:
            index = split.index("pdf")
            index_start_2 = index + 2
            split = split[0:index] + split[index_start_2:]

        # some names are only different by common or unnecessary words,
        # so remove them
        common_words = [
            "test",
            "testing",
            "antigen",
            "rapid",
            "for",
            "use",
            "selftests",
            "and",
            "nasal",
            "swab",
            "oral",
            "fluid",
            "self",
            "kit",
        ]
        norm = [w for w in split if w not in common_words]

        norm_slug = "-".join(norm)

        result = ProductMatchInfo(
            artg=artg,
            title=new_name,
            name=name,
            slug=norm_slug,
            is_poct=is_poct,
            is_self=is_self,
            is_lab=is_lab,
        )
        return result

    @classmethod
    def _slugify(cls, value, allow_unicode=False) -> str:
        """
        Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
        dashes to single dashes. Remove characters that aren't alphanumerics,
        underscores, or hyphens. Convert to lowercase. Also strip leading and
        trailing whitespace, dashes, and underscores.
        """
        # from django: https://github.com/django/django/blob/4.2/django/utils/text.py
        value = str(value)
        if allow_unicode:
            value = unicodedata.normalize("NFKC", value)
        else:
            value = (
                unicodedata.normalize("NFKD", value)
                .encode("ascii", "ignore")
                .decode("ascii")
            )
        value = re.sub(r"[^\w\s-]", "", value.lower())
        return re.sub(r"[-\s]+", "-", value).strip("-_")


@dataclasses.dataclass
class ProductInfo:
    details_url: typing.Optional[str] = dataclasses.field(default=None)
    sponsor: typing.Optional[str] = dataclasses.field(default=None)
    date_approved: typing.Optional[str] = dataclasses.field(default=None)
    manufacturer: typing.Optional[str] = dataclasses.field(default=None)
    test_type: typing.Optional[str] = dataclasses.field(default=None)
    intended_use: typing.Optional[str] = dataclasses.field(default=None)
    date_updated: typing.Optional[str] = dataclasses.field(default=None)
    type_of_use: typing.Optional[str] = dataclasses.field(default=None)
    instructions_url: typing.Optional[str] = dataclasses.field(default=None)
    sample_type: typing.Optional[str] = dataclasses.field(default=None)
    sensitivity: typing.Optional[str] = dataclasses.field(default=None)
    expiry: typing.Optional[str] = dataclasses.field(default=None)
    comment: typing.Optional[str] = dataclasses.field(default=None)
    variants: typing.Optional[str] = dataclasses.field(default=None)
    review_wild: typing.Optional[str] = dataclasses.field(default=None)
    review_delta: typing.Optional[str] = dataclasses.field(default=None)
    review_omicron: typing.Optional[str] = dataclasses.field(default=None)
    review_quality: typing.Optional[str] = dataclasses.field(default=None)
    errors: dict[str, set] = dataclasses.field(default_factory=dict)

    def set_prop(self, key: str, value: str):
        if not hasattr(self, key) or key == "errors":
            raise ValueError({key: value})

        existing = getattr(self, key)
        if existing is None:
            setattr(self, key, value)

        elif existing != value:
            key = f"{key}_mismatch"
            if key not in self.errors:
                self.errors[key] = set()
            self.errors[key].add(value)


@dataclasses.dataclass
class RatInfo:
    artg: str
    title: str
    details_url: str
    sponsor: str
    date_approved: str
    manufacturer: str
    test_type: str
    intended_use: str
    date_updated: str
    type_of_use: str
    instructions_url: str
    sample_type: str
    sensitivity: str
    expiry: str
    comment: str
    variants: str
    review_wild: str
    review_delta: str
    review_omicron: str
    review_quality: str
    errors: str
