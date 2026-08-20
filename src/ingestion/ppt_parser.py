from __future__ import annotations

from pathlib import Path
import tempfile

from .pptx_parser import PptxParser


class PptParser:
    supported = (".ppt",)

    def parse(self, path: str | Path):
        ppt_path = Path(path)
        with tempfile.TemporaryDirectory() as tmpdir:
            converted = Path(tmpdir) / f"{ppt_path.stem}.pptx"
            self._convert_with_powerpoint(ppt_path, converted)
            return PptxParser().parse(converted)

    def _convert_with_powerpoint(self, source: Path, target: Path) -> None:
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError("PPT parsing requires Microsoft PowerPoint and pywin32.") from exc

        powerpoint = None
        presentation = None
        try:
            pythoncom.CoInitialize()
            powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
            presentation = powerpoint.Presentations.Open(str(source), ReadOnly=True, WithWindow=False)
            presentation.SaveAs(str(target), 24)
        finally:
            if presentation is not None:
                presentation.Close()
            if powerpoint is not None:
                powerpoint.Quit()
            pythoncom.CoUninitialize()
