# scripts/docs.py

import io
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LODE_API = "https://lode.opencitations.net/build"
SOURCE = Path("project") / "tbox.ttl"
OUT = Path("project") / "docs"


def build(source, out):
    """Build the LODE site with the LODE 2.0 web service (`POST /build`).

    Uploads `source` to lode.opencitations.net and unpacks the returned ZIP.

    Args:
        source: Ontology file to document.
        out: Output directory.

    Raises:
        SystemExit: If the request fails.
    """
    boundary = uuid.uuid4().hex
    fields = {"read_as": "owl", "lang": "en", "warnings": "true"}
    body = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
             f"Content-Type: text/turtle\r\n\r\n").encode() + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = Request(LODE_API, data=body, method="POST",
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=180) as response:
            data = response.read()
    except HTTPError as e:
        print(f"Error: LODE returned HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
        sys.exit(1)
    except URLError as e:
        print(f"Error: cannot reach {LODE_API}: {e.reason}")
        sys.exit(1)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        print(f"Error: LODE did not return a ZIP: {data[:300].decode(errors='replace')}")
        sys.exit(1)
    out.mkdir(parents=True)
    archive.extractall(out)  # extractall drops absolute paths and ".." components
    top = list(out.iterdir())
    if len(top) == 1 and top[0].is_dir():  # the site comes in one folder named after the file
        for item in top[0].iterdir():
            item.rename(out / item.name)
        top[0].rmdir()
    print(f"Built with {LODE_API} ({len(archive.namelist())} files)")


def main():
    """Generate the HTML documentation of the current model with the LODE 2.0 web service.

    Documents `project/tbox.ttl` (written by `merge`, with the ontology header
    from `ontology.yaml`) into `project/docs/`, replacing its previous content.
    Open `project/docs/index.html`, or `/project/docs/index.html` in the web
    interface. `project/tbox.ttl` is uploaded to lode.opencitations.net.

    Raises:
        SystemExit: If `project/tbox.ttl` is missing or the build fails.
    """
    if not SOURCE.exists():
        print(f"Error: {SOURCE} not found. Run merge first.")
        sys.exit(1)
    if OUT.exists():
        shutil.rmtree(OUT)  # generated: stale pages of removed terms would linger
    build(SOURCE, OUT)
    index = next(OUT.glob("index.html"), None) or next(OUT.rglob("*.html"), None)
    print(f"Documentation: {index or OUT}")


if __name__ == "__main__":
    main()
