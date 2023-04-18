# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
import pathlib

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

from leaf_focus.pdf import xpdf, model
from scrapy.pipelines import files


class PdfExtractTextFilesPipeline(files.FilesPipeline):
    def __init__(self, store_uri, download_func=None, settings=None):
        super().__init__(store_uri, download_func, settings)
        self._xpdf = xpdf.XpdfProgram(pathlib.Path(settings.get("XPDF_DIR")))
        self._xpdf_text_args = model.XpdfTextArgs(
            use_table_layout=True,
            line_end_type="unix",
            use_verbose=True,
        )
        self._store_base_abs = pathlib.Path(self.store.basedir).absolute()

    def item_completed(self, results, item, info):
        adapter = ItemAdapter(super().item_completed(results, item, info))
        item_files = adapter.get("files", [])
        for file in item_files:
            pdf_file = pathlib.Path(self._store_base_abs, file.get("path"))
            output_dir = pdf_file.parent
            prog_result = self._xpdf.text(pdf_file, output_dir, self._xpdf_text_args)
            text_file = prog_result.output_path.relative_to(self._store_base_abs)
            file["pdf_text"] = "/".join(text_file.parts)
        return item
