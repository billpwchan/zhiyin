import os
import tempfile

# zhiyin.store reads ZHIYIN_DATA at import time; every test run gets its own empty data folder.
os.environ["ZHIYIN_DATA"] = tempfile.mkdtemp(prefix="zhiyin-test-")
# accounts without a chosen language follow the machine's locale; pin it so messages read the same everywhere
os.environ["ZHIYIN_LANG"] = "zh-Hans"
