#!/usr/bin/env python3
"""Google Drive pull/push/list using the Sheets OAuth token (has drive scope).
Usage:
  gdrive.py list
  gdrive.py pull <fileId> <out.mp4>
  gdrive.py push <file> "<drive name>" [parentFileId]
Never prints token/secret values.
"""
import json, os, sys, urllib.request, urllib.parse

TOK = os.path.expanduser("~/.config/gcloud/sheets-token.json")

def token():
    d = json.load(open(TOK))
    data = urllib.parse.urlencode({
        "client_id": d["client_id"], "client_secret": d["client_secret"],
        "refresh_token": d["refresh_token"], "grant_type": "refresh_token",
    }).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(d["token_uri"], data=data)))["access_token"]

def _get(tok, url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + tok}))

def cmd_list(tok):
    q = urllib.parse.urlencode({
        "q": "mimeType contains 'video/' and trashed=false", "orderBy": "modifiedTime desc",
        "pageSize": "15", "fields": "files(id,name,size,modifiedTime,parents)",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true", "corpora": "allDrives",
    })
    for f in json.load(_get(tok, "https://www.googleapis.com/drive/v3/files?" + q)).get("files", []):
        mb = int(f.get("size", 0)) / 1e6 if f.get("size") else 0
        print(f"{f['modifiedTime'][:16]}  {mb:6.1f}MB  {f['name']}   id={f['id']}")

def cmd_pull(tok, fid, out):
    url = f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media&supportsAllDrives=true"
    with _get(tok, url) as r, open(out, "wb") as f:
        while (chunk := r.read(1 << 20)):
            f.write(chunk)
    print("pulled", out, os.path.getsize(out) // 1_000_000, "MB")

def cmd_push(tok, path, name, parent=None):
    if parent is None:
        # default beside the most-recent video's folder
        parent = None
    body = open(path, "rb").read()
    meta = {"name": name}
    if parent:
        meta["parents"] = [parent]
    b = "====b"
    pre = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + json.dumps(meta) +
           f"\r\n--{b}\r\nContent-Type: video/mp4\r\n\r\n").encode()
    payload = pre + body + f"\r\n--{b}--".encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true",
        data=payload, headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/related; boundary={b}"})
    res = json.load(urllib.request.urlopen(req))
    print("pushed:", res["name"], "https://drive.google.com/file/d/" + res["id"] + "/view")

if __name__ == "__main__":
    tok = token()
    c = sys.argv[1] if len(sys.argv) > 1 else "list"
    if c == "list": cmd_list(tok)
    elif c == "pull": cmd_pull(tok, sys.argv[2], sys.argv[3])
    elif c == "push": cmd_push(tok, sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else: print(__doc__)
