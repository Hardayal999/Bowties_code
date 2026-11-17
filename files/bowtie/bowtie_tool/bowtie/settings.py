"""
settings.py
Fixed settings that are the same for every project.
Where things are in a particular hazard log is NOT here: that is in mapping.json.
"""

OUTPUT_FOLDER = "bowtie_output"
MAPPING_FILE = "mapping.json"

# --- Riskrunner -------------------------------------------------------------
RISKRUNNER_SITE = "https://riskrunner.app"        # the address people open in a browser
RISKRUNNER_API = "https://riskrunner.app/api"     # the address programs talk to
SANDBOX_PREFIX = "SANDBOX bowtie test"            # every assessment the loader creates starts with this
