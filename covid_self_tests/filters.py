class TgaRatsSensitivityFilter:
    def __init__(self, feed_options):
        self.feed_options = feed_options

    def accepts(self, item):
        return item["data-group"] == "sensitivity"


class TgaRatsDetailsFilter:
    def __init__(self, feed_options):
        self.feed_options = feed_options

    def accepts(self, item):
        return item["data-group"] == "details"


class TgaRatsDetailsItemFilter:
    def __init__(self, feed_options):
        self.feed_options = feed_options

    def accepts(self, item):
        return item["data-group"] == "details-item"


class TgaRatsReviewFilter:
    def __init__(self, feed_options):
        self.feed_options = feed_options

    def accepts(self, item):
        return item["data-group"] == "review"
