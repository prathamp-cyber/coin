"""
Core blockchain implementation: Transaction, Block, and Blockchain.
"""

import hashlib
import json
import time
from typing import Any

from config import (
    DIFFICULTY,
    GENESIS_TIMESTAMP,
    MINING_REWARD,
    SYSTEM_ADDRESS,
)
from wallet import Wallet, verify_signature


class Transaction:
    """
    Represents a value transfer between two addresses, or a mining reward.
    """

    def __init__(
        self,
        sender: str,
        receiver: str,
        amount: int,
        data: str = "",
        timestamp: float | None = None,
        signature: str = "",
    ) -> None:
        self.sender: str = sender
        self.receiver: str = receiver
        self.amount: int = amount
        self.data: str = data
        self.timestamp: float = time.time() if timestamp is None else timestamp
        self.signature: str = signature

    def payload(self) -> bytes:
        """
        Return the canonical bytes representation of transaction data to be signed.
        Uses sorted keys and compact separators to ensure deterministic serialization.
        """
        data_to_serialize = {
            "amount": self.amount,
            "data": self.data,
            "receiver": self.receiver,
            "sender": self.sender,
            "timestamp": self.timestamp,
        }
        return json.dumps(data_to_serialize, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def tx_id(self) -> str:
        """Calculate the unique SHA-256 identifier of the transaction payload."""
        return hashlib.sha256(self.payload()).hexdigest()

    def sign_with(self, wallet: Wallet) -> None:
        """Sign the transaction payload with the sender's wallet."""
        self.signature = wallet.sign(self.payload())

    def is_valid_signature(self) -> bool:
        """
        Validate the transaction's signature against the sender's public key address.
        Reward transactions from SYSTEM_ADDRESS are exempt from signature checks.
        """
        if self.sender == SYSTEM_ADDRESS:
            return True
        if not self.signature:
            return False
        return verify_signature(self.sender, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        """Convert transaction into a serializable dictionary."""
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "data": self.data,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transaction":
        """Reconstruct a Transaction instance from a dictionary."""
        return cls(
            sender=d["sender"],
            receiver=d["receiver"],
            amount=d["amount"],
            data=d.get("data", ""),
            timestamp=d["timestamp"],
            signature=d.get("signature", ""),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transaction):
            return False
        return self.to_dict() == other.to_dict()


class Block:
    """
    A block containing a list of transactions, a link to the previous block,
    and a Proof of Work nonce.
    """

    def __init__(
        self,
        index: int,
        timestamp: float,
        transactions: list[Transaction],
        previous_hash: str,
        nonce: int = 0,
        hash: str = "",
    ) -> None:
        self.index: int = index
        self.timestamp: float = timestamp
        self.transactions: list[Transaction] = transactions
        self.previous_hash: str = previous_hash
        self.nonce: int = nonce
        self.hash: str = hash if hash else self.compute_hash()

    def compute_hash(self) -> str:
        """
        Calculate the SHA-256 hash of the block contents using deterministic JSON serialization.
        """
        block_data = {
            "index": self.index,
            "nonce": self.nonce,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
        }
        serialized = json.dumps(block_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert block into a serializable dictionary."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Block":
        """Reconstruct a Block instance from a dictionary."""
        transactions = [Transaction.from_dict(tx_dict) for tx_dict in d["transactions"]]
        return cls(
            index=d["index"],
            timestamp=d["timestamp"],
            transactions=transactions,
            previous_hash=d["previous_hash"],
            nonce=d["nonce"],
            hash=d.get("hash", ""),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Block):
            return False
        return self.to_dict() == other.to_dict()


class Blockchain:
    """
    Manages the ledger of blocks, mempool of pending transactions,
    balance tracking, mining, and consensus validation.
    """

    def __init__(self) -> None:
        self.chain: list[Block] = [self.create_genesis_block()]
        self.pending_transactions: list[Transaction] = []

    @staticmethod
    def create_genesis_block() -> Block:
        """
        Create a deterministic genesis block identical across all network nodes.
        Index is 0, timestamp is fixed, previous_hash is '0', nonce is 0, no transactions.
        """
        return Block(
            index=0,
            timestamp=GENESIS_TIMESTAMP,
            transactions=[],
            previous_hash="0",
            nonce=0,
        )

    def get_balance(self, address: str) -> int:
        """
        Calculate the confirmed balance of an address by scanning all blocks in the chain.
        Balance = total received - total sent.
        """
        balance = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx.receiver == address:
                    balance += tx.amount
                if tx.sender == address:
                    balance -= tx.amount
        return balance

    def add_transaction(self, tx: Transaction) -> tuple[bool, str]:
        """
        Validate and queue a transaction into the mempool.
        Returns (True, 'ok') if valid, or (False, reason) if rejected.
        """
        # 1. Amount must be a positive integer
        if not isinstance(tx.amount, int) or isinstance(tx.amount, bool) or tx.amount <= 0:
            return False, "Transaction amount must be a positive integer"

        # 2. External transactions cannot claim to originate from SYSTEM_ADDRESS
        if tx.sender == SYSTEM_ADDRESS:
            return False, "Cannot send transactions with sender SYSTEM"

        # 3. Sender and receiver cannot be identical
        if tx.sender == tx.receiver:
            return False, "Sender cannot be receiver"

        # 4. Digital signature must be valid
        if not tx.is_valid_signature():
            return False, "Invalid transaction signature"

        # 5. Prevent duplicate transactions (in mempool or already mined)
        tx_id = tx.tx_id()
        if any(pending.tx_id() == tx_id for pending in self.pending_transactions):
            return False, "Transaction is already pending in mempool"
        if any(mined_tx.tx_id() == tx_id for block in self.chain for mined_tx in block.transactions):
            return False, "Transaction already exists in chain"

        # 6. Check available balance: confirmed balance minus already pending outgoing amounts
        confirmed_balance = self.get_balance(tx.sender)
        pending_outgoing = sum(
            p.amount for p in self.pending_transactions if p.sender == tx.sender
        )
        available_balance = confirmed_balance - pending_outgoing
        if available_balance < tx.amount:
            return (
                False,
                f"Insufficient balance: available {available_balance}, requested {tx.amount}",
            )

        self.pending_transactions.append(tx)
        return True, "ok"

    def mine_pending_transactions(self, miner_address: str) -> Block:
        """
        Package pending transactions into a new block, add the mining reward,
        solve the Proof of Work puzzle, append the block to the chain,
        and clean up included transactions from the mempool.
        """
        # Create the mining reward transaction (first in the block)
        reward_tx = Transaction(
            sender=SYSTEM_ADDRESS,
            receiver=miner_address,
            amount=MINING_REWARD,
            data="",
            timestamp=time.time(),
            signature="",
        )

        transactions_to_include = [reward_tx] + list(self.pending_transactions)

        # Assemble new block linking to current tip
        new_block = Block(
            index=len(self.chain),
            timestamp=time.time(),
            transactions=transactions_to_include,
            previous_hash=self.chain[-1].hash,
            nonce=0,
        )

        # Run Proof of Work until hash meets difficulty target
        target_prefix = "0" * DIFFICULTY
        while not new_block.hash.startswith(target_prefix):
            new_block.nonce += 1
            new_block.hash = new_block.compute_hash()

        # Append block to chain
        self.chain.append(new_block)

        # Remove included transactions from pending list
        included_ids = {tx.tx_id() for tx in transactions_to_include}
        self.pending_transactions = [
            tx for tx in self.pending_transactions if tx.tx_id() not in included_ids
        ]

        return new_block

    @classmethod
    def is_valid_chain(cls, chain: list[Block]) -> tuple[bool, str]:
        """
        Validate an entire blockchain from genesis to tip.
        Returns (True, 'ok') or (False, reason).
        """
        if not chain:
            return False, "Chain is empty"

        # Check deterministic genesis block
        expected_genesis = cls.create_genesis_block()
        if chain[0].to_dict() != expected_genesis.to_dict():
            return False, "Invalid genesis block"

        target_prefix = "0" * DIFFICULTY
        balances: dict[str, int] = {}

        # Validate subsequent blocks and replay transactions
        for i in range(1, len(chain)):
            current_block = chain[i]
            prev_block = chain[i - 1]

            # Index continuity
            if current_block.index != prev_block.index + 1:
                return (
                    False,
                    f"Invalid block index at block {i}: expected {prev_block.index + 1}, got {current_block.index}",
                )

            # Previous hash linkage
            if current_block.previous_hash != prev_block.hash:
                return False, f"Broken previous_hash link at block {i}"

            # Stored hash matches computed hash
            if current_block.hash != current_block.compute_hash():
                return False, f"Stored hash does not match computed hash at block {i}"

            # Hash meets Proof of Work difficulty
            if not current_block.hash.startswith(target_prefix):
                return False, f"Block {i} hash does not meet difficulty {DIFFICULTY}"

            # Block must have at least the reward transaction
            if not current_block.transactions:
                return False, f"Block {i} has no transactions"

            # Exactly one reward transaction, which must be first, with amount == MINING_REWARD
            reward_tx = current_block.transactions[0]
            if reward_tx.sender != SYSTEM_ADDRESS or reward_tx.amount != MINING_REWARD:
                return (
                    False,
                    f"First transaction of block {i} must be mining reward of {MINING_REWARD} from {SYSTEM_ADDRESS}",
                )

            # Check that there are no additional reward transactions and all signatures are valid
            for tx_idx, tx in enumerate(current_block.transactions[1:], start=1):
                if tx.sender == SYSTEM_ADDRESS:
                    return (
                        False,
                        f"Block {i} contains multiple reward transactions (found at index {tx_idx})",
                    )
                if not isinstance(tx.amount, int) or isinstance(tx.amount, bool) or tx.amount <= 0:
                    return False, f"Block {i} transaction {tx_idx} amount must be positive integer"
                if tx.sender == tx.receiver:
                    return False, f"Block {i} transaction {tx_idx} sender equals receiver"
                if not tx.is_valid_signature():
                    return False, f"Block {i} transaction {tx_idx} has invalid signature"

            # Replay all transactions to verify no sender's balance ever goes negative
            for tx in current_block.transactions:
                if tx.sender == SYSTEM_ADDRESS:
                    balances[tx.receiver] = balances.get(tx.receiver, 0) + tx.amount
                else:
                    sender_balance = balances.get(tx.sender, 0)
                    if sender_balance < tx.amount:
                        return (
                            False,
                            f"Negative balance for sender {tx.sender} during replay in block {i}: balance {sender_balance}, sent {tx.amount}",
                        )
                    balances[tx.sender] = sender_balance - tx.amount
                    balances[tx.receiver] = balances.get(tx.receiver, 0) + tx.amount

        return True, "ok"

    def add_block(self, block: Block) -> tuple[bool, str]:
        """
        Append a single new block to the end of the chain.
        Validates index continuity, previous hash linkage, and full proposed chain validity.
        """
        if not self.chain:
            return False, "Chain is empty"

        last_block = self.chain[-1]

        # 1. Check index continuity
        if block.index != last_block.index + 1:
            return (
                False,
                f"Invalid block index: expected {last_block.index + 1}, got {block.index}",
            )

        # 2. Check previous_hash linkage
        if block.previous_hash != last_block.hash:
            return (
                False,
                f"Broken previous_hash link: block previous_hash {block.previous_hash} does not match tip {last_block.hash}",
            )

        # 3. Validate entire proposed chain
        candidate_chain = self.chain + [block]
        valid, reason = self.is_valid_chain(candidate_chain)
        if not valid:
            return False, f"Invalid block: {reason}"

        # 4. Append block
        self.chain.append(block)

        # 5. Remove included transactions from pending list
        mined_tx_ids = {tx.tx_id() for tx in block.transactions}
        self.pending_transactions = [
            tx for tx in self.pending_transactions if tx.tx_id() not in mined_tx_ids
        ]

        return True, "ok"

    def replace_chain_if_longer(self, new_chain: list[Block] | "Blockchain") -> bool:
        """
        Consensus rule: replace the current chain if new_chain is strictly longer
        and passes full blockchain validation.
        Cleans up any pending transactions that are now included in the new chain.
        """
        candidate_blocks = new_chain.chain if isinstance(new_chain, Blockchain) else new_chain

        if len(candidate_blocks) <= len(self.chain):
            return False

        valid, _ = self.is_valid_chain(candidate_blocks)
        if not valid:
            return False

        self.chain = list(candidate_blocks)

        # Remove any transaction from pending list if it is now in the chain
        mined_tx_ids = {tx.tx_id() for block in self.chain for tx in block.transactions}
        self.pending_transactions = [
            tx for tx in self.pending_transactions if tx.tx_id() not in mined_tx_ids
        ]
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert the entire blockchain into a serializable dictionary."""
        return {"chain": [block.to_dict() for block in self.chain]}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | list[dict[str, Any]]) -> "Blockchain":
        """
        Reconstruct a Blockchain instance from a dictionary or list of block dictionaries.
        """
        if isinstance(d, list):
            block_dicts = d
        elif isinstance(d, dict) and "chain" in d:
            block_dicts = d["chain"]
        else:
            raise ValueError("Expected a dict with 'chain' key or a list of block dicts")

        bc = cls.__new__(cls)
        bc.chain = [Block.from_dict(b_dict) for b_dict in block_dicts]
        bc.pending_transactions = []
        return bc

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Blockchain):
            return False
        return self.chain == other.chain and self.pending_transactions == other.pending_transactions
