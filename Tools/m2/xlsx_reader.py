"""Minimal read-only .xlsx reader (stdlib only) used by the M2 pact/trait generator."""
import re
import zipfile
import xml.etree.ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_workbook(path):
    """Return {sheet_name: [[cell, ...], ...]} with merged cells left blank."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels.iter(_REL + "Relationship")}
        sheets = {}
        for s in wb.find("m:sheets", _NS):
            rid = s.get("{%s}id" % _NS["r"])
            t = target[rid].lstrip("/")
            t = t if t.startswith("xl/") else "xl/" + t
            root = ET.fromstring(z.read(t))
            rows = []
            for row in root.iter("{%s}row" % _NS["m"]):
                cells = {}
                for c in row.findall("m:c", _NS):
                    v = c.find("m:v", _NS)
                    typ = c.get("t")
                    if typ == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif typ == "inlineStr":
                        val = "".join(t.text or "" for t in c.iter("{%s}t" % _NS["m"]))
                    elif v is not None:
                        val = v.text
                        try:
                            f = float(val)
                            val = int(f) if f.is_integer() else f
                        except ValueError:
                            pass
                    else:
                        val = None
                    cells[_col_index(c.get("r"))] = val
                if cells:
                    width = max(cells) + 1
                    rows.append([cells.get(i) for i in range(width)])
                else:
                    rows.append([])
            sheets[s.get("name")] = rows
        return sheets
