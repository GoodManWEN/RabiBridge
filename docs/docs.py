import os
import hashlib
from loguru import logger
from pipeit import *

proj_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
docs_dir = os.path.join(proj_dir, "docs")
tmp_dir = os.path.join(proj_dir, "tmp")

def get_html_files(dir_path: str):
    ret = []
    for root, _, files in os.walk(dir_path):
        for file in files:
            if file.endswith(".html"):
                ret.append([file, os.path.join(root, file)])
    return ret

current_html_pages = os.listdir(docs_dir) | Filter(lambda x: x.endswith(".html")) | Map(lambda x: [x, os.path.join(docs_dir, x)]) | dict
new_html_pages = dict(get_html_files(tmp_dir))


new_set = set([x for x in new_html_pages.keys()]) - set([x for x in current_html_pages.keys()])
remove_set = set([x for x in current_html_pages.keys()]) - set([x for x in new_html_pages.keys()])
mod_set = set([x for x in new_html_pages.keys()]) & set([x for x in current_html_pages.keys()])

# new
for page_name in new_set:
    new_path = os.path.join(docs_dir, page_name)
    with open(new_html_pages[page_name], "r", encoding='utf-8') as fa:
        content = fa.read()
        with open(new_path, "w", encoding='utf-8') as fb:
            fb.write(content)
            logger.info(f"New: {new_path}")

# remove
for page_name in remove_set:
    remove_path = current_html_pages[page_name]
    try:
        os.remove(remove_path)
        logger.info(f"Remove: {remove_path}")
    except:
        logger.warning(f"Remove: {remove_path} failed")

# mod
for page_name in mod_set:
    current_path = current_html_pages[page_name]
    new_path = new_html_pages[page_name]
    with open(current_path, "r", encoding='utf-8') as fa:
        current_content = fa.read()
    with open(new_path, "r", encoding='utf-8') as fb:
        new_content = fb.read()
    if hashlib.sha256(current_content.encode('utf-8')).hexdigest() != hashlib.sha256(new_content.encode('utf-8')).hexdigest():
        # content changed
        with open(current_path, "w", encoding='utf-8') as fc:
            fc.write(new_content)
            logger.info(f"Mod: {current_path}")
