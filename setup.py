import setuptools
import os
from datetime import datetime
thelibFolder = os.path.dirname(os.path.realpath(__file__))
requirementPath = os.path.join(thelibFolder, 'requirements.txt')
install_requires = []
if os.path.isfile(requirementPath):
    with open(requirementPath) as f:
        install_requires = f.read().splitlines()

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="aufit",
    version=datetime.now().strftime("%Y.%m.%d"),
    author="deorth-kku",
    author_email="deorth_kku@outlook.com",
    description="Anime Upcale & Frame Interpolation Tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/deorth_kku/aufit",
    install_requires=install_requires,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(),
    python_requires='>=3.9',
    entry_points={
        'console_scripts': ['aufit=aufit.__main__:main']
    }
)
