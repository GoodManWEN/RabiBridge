from setuptools import setup, find_packages
from requests import get as rget
from bs4 import BeautifulSoup
import logging , sys

# init logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
sh = logging.StreamHandler(stream=sys.stdout) 
format = logging.Formatter("%(message)s")#("%(asctime)s - %(message)s") 
sh.setFormatter(format)
logger.addHandler(sh)

#
def get_install_requires(filename):
    def cut_word(x):
        if '[' in x:
            x = x[:x.index('[')]
        return x.strip()
    with open(filename,'r') as f:
        lines = f.readlines()
    return [cut_word(x) for x in lines]

# 
url = 'https://github.com/GoodManWEN/RabiBridge'
release = '{}/releases/latest'.format(url)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36",
    "Connection": "keep-alive",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.8"
}

html = BeautifulSoup(rget(url , headers).text ,'lxml')
description = html.find('meta' ,{'name':'description'}).get('content')
for kw in (' - GitHub', ' - GoodManWEN'):
    if ' - GitHub' in description:
        description = description[:description.index(' - GitHub')]
html = BeautifulSoup(rget(release , headers).text ,'lxml')
version = html.find('a', {'class': 'Link--muted'}).find('span').text.strip()
if ':' in version:
    version = version[:version.index(':')].strip()
logger.info("description: {}".format(description))
logger.info("version: {}".format(version))

#
with open('README.md','r',encoding='utf-8') as f:
    long_description_lines = f.readlines()

long_description_lines_copy = long_description_lines[:]
long_description_lines_copy.insert(0,'r"""\n')
long_description_lines_copy.append('"""\n')

# update __init__ docs
with open('rabibridge/__init__.py','r',encoding='utf-8') as f:
    init_content = f.readlines()

for line in init_content:
    if line == "__version__ = ''\n":
        long_description_lines_copy.append("__version__ = '{}'\n".format(version))
    else:
        long_description_lines_copy.append(line)

with open('rabibridge/__init__.py','w',encoding='utf-8') as f:
    f.writelines(long_description_lines_copy)

setup(
    name="RabiBridge", 
    version=version,
    author="WEN",
    description=description,
    long_description=''.join(long_description_lines),
    long_description_content_type="text/markdown",
    url="https://github.com/GoodManWEN/RabiBridge",
    packages = find_packages(),
    install_requires = get_install_requires('requirements.txt'),
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Microsoft :: Windows',
    ],
    python_requires='>=3.8',
    keywords=["RabiBridge" ,"rabbitmq", "rpc", "fastapi"]
)