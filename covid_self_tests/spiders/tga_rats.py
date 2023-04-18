import re
import typing

import scrapy


class TgaRatsSpider(scrapy.Spider):
    name = "tga-rats"

    _url_test_sensitivity = "/".join(
        [
            "https://www.tga.gov.au",
            "products",
            "covid-19",
            "covid-19-tests",
            "covid-19-rapid-antigen-self-tests-home-use",
            "covid-19-rapid-antigen-self-tests-are-approved-australia",
        ]
    )
    _url_test_details = "https://www.tga.gov.au/resources/covid-19-test-kits"
    _url_test_review = "/".join(
        [
            "https://www.tga.gov.au",
            "products",
            "covid-19",
            "covid-19-tests",
            "post-market-review-antigen-and-rapid-antigen-tests",
        ]
    )

    start_urls = [
        _url_test_sensitivity,
        _url_test_details,
        _url_test_review,
    ]

    def parse(self, response, **kwargs):
        sensitivity_data = self._parse_test_sensitivity(response, **kwargs)
        for item in sensitivity_data:
            yield item

        detailed_data = self._parse_test_details(response, **kwargs)
        for item in detailed_data:
            yield item

        review_data = self._parse_test_review(response, **kwargs)
        for item in review_data:
            yield item

    def _parse_test_sensitivity(
        self, response, **kwargs
    ) -> typing.Iterable[typing.Union[dict, str]]:
        if not response.url.startswith(self._url_test_sensitivity):
            return None

        table = response.css(".dataTable")
        table_head = table.css("thead")

        headers = table_head.xpath("./tr/td//text()").getall()

        table_body = table.css("tbody")
        for row in table_body.xpath("./tr"):
            item = {"data-group": "sensitivity"}
            for header, cell in zip(headers, row.xpath("./td")):
                texts = cell.xpath(".//text()").getall()
                item[header] = self._combine_text(" ", texts)

                urls = self._combine_urls(response, cell, item.get("urls", ""))
                item["urls"] = urls

            yield item

    def _parse_test_details(
        self, response, **kwargs
    ) -> typing.Iterable[typing.Union[dict, str]]:
        if not response.url.startswith(self._url_test_details):
            return None

        container = response.css(".health-listing")

        for entry in container.css("article"):
            date_raw = entry.xpath(
                './/*[contains(@class, "summary__date")]//text()'
            ).getall()
            date = self._combine_text(" ", date_raw).strip(" |")

            title_raw = entry.xpath('.//*[contains(@class, "summary__title")]')
            title = self._combine_text(
                " ", title_raw.xpath(".//text()").getall()
            ).strip()
            url = self._combine_urls(response, title_raw)

            summary_raw = entry.xpath(
                './/*[contains(@class, "summary__summary")]//text()'
            ).getall()
            summary = self._combine_text(" ", summary_raw).strip(" |")

            yield {
                "data-group": "details",
                "date": date,
                "title": title,
                "url": url,
                "summary": summary,
            }
            yield scrapy.Request(url, self._parse_test_detail)

        next_anchor = response.xpath('//a[@rel="next"]')
        if next_anchor:
            next_url = response.urljoin(next_anchor.xpath("./@href").get())
            yield scrapy.Request(next_url)

    def _parse_test_detail(
        self, response, **kwargs
    ) -> typing.Iterable[typing.Union[dict, str]]:
        if not response.url.startswith(self._url_test_details):
            return None

        container = response.css(".definition-list")
        labels = container.xpath(".//*[contains(@class,'field__label')]")
        items = container.xpath(".//*[contains(@class,'field__item')]")

        data = {
            "url": response.url,
            "data-group": "details-item",
        }

        for label, item in zip(labels, items):
            key = self._combine_text(" ", label.xpath(".//text()").getall())
            value = self._combine_text(" ", item.xpath(".//text()").getall())
            data[key] = value

        yield data

    def _parse_test_review(
        self, response, **kwargs
    ) -> typing.Iterable[typing.Union[dict, str]]:
        if not response.url.startswith(self._url_test_review):
            return []

        url_raw = response.css("a[href$='pdf']").xpath("./@href").get()
        url = response.urljoin(url_raw)
        yield {
            "data-group": "review",
            "file_urls": [url],
        }

    def _combine_text(self, sep: str, texts) -> str:
        raw = sep.join([t.strip() for t in texts if t and t.strip()]).strip()
        result = self._norm_whitespace(raw)
        return result

    def _combine_urls(self, response, element, existing: str = "") -> str:
        sep = " || "

        urls_raw = element.xpath(".//a/@href").getall()
        urls = [response.urljoin(u.strip()) for u in urls_raw if u and u.strip()]

        existing_urls = [u for u in existing.split(sep) if u and u.strip()]

        result = sep.join(urls + existing_urls).strip()
        return result

    def _norm_whitespace(self, value: str) -> str:
        pattern = re.compile(r"(\s|\u180B|\u200B|\u200C|\u200D|\u2060|\uFEFF)+")
        result = pattern.sub(" ", value)
        return result
