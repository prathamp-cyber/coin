"""
Configuration constants for the MyCoin educational cryptocurrency blockchain.
"""

# Coin identity
COIN_NAME: str = "MyCoin"
SYMBOL: str = "MYC"

# Proof of Work difficulty: number of leading zeros required in a valid block hash
DIFFICULTY: int = 5

# Reward granted to miners per mined block
MINING_REWARD: int = 50

# Fixed timestamp for deterministic genesis block creation across nodes
GENESIS_TIMESTAMP: float = 0

# Special sender address designating system-minted rewards
SYSTEM_ADDRESS: str = "SYSTEM"

# Networking and persistence constants for node operations
DEFAULT_PORT: int = 5000
SYNC_INTERVAL_SECONDS: int = 10
REQUEST_TIMEOUT_SECONDS: int = 3
DATA_DIR: str = "data"
