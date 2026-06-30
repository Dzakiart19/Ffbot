"""
Token manager — simple account loader for admin endpoints.
Actual JWT creation is handled per-request in like_api.py via get_jwt.py
"""
import json
import os
import logging

logger = logging.getLogger(__name__)

REGION_CONFIG = {
    "ID":     "config/sg_config.json",
    "SG":     "config/sg_config.json",
    "EUROPE": "config/europe_config.json",
    "RU":     "config/europe_config.json",
    "IND":    "config/ind_config.json",
    "BR":     "config/br_config.json",
    "US":     "config/br_config.json",
}


class TokenManager:
    def _load(self, region: str) -> list:
        path = REGION_CONFIG.get(region.upper(), "config/sg_config.json")
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Load accounts [{region}]: {e}")
        return []

    def count_accounts(self, region: str) -> int:
        return len(self._load(region.upper()))

    def add_account(self, region: str, uid: str, password: str) -> bool:
        path = REGION_CONFIG.get(region.upper(), "config/sg_config.json")
        try:
            accounts = self._load(region)
            if any(str(a["uid"]) == str(uid) for a in accounts):
                return False
            accounts.append({"uid": str(uid), "password": str(password)})
            with open(path, "w") as f:
                json.dump(accounts, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Add account error: {e}")
        return False

    # kept for compatibility with app.py stats endpoint
    def get_tokens(self, region: str) -> list:
        return [a["uid"] for a in self._load(region)]


token_manager = TokenManager()
