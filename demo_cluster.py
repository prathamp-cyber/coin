"""
Automated end-to-end multi-node cluster demonstration and integration test.
Launches 3 real MyCoin nodes on ports 5100, 5101, and 5102, runs complete
workflow and network consensus tests, and verifies offline node catch-up.
"""

import copy
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
import requests


def wait_for_node(url: str, timeout: float = 20.0) -> bool:
    """Poll a node until it responds to GET / or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def run_demo() -> int:
    temp_dir = tempfile.mkdtemp(prefix="mycoin_cluster_")
    proc_a = None
    proc_b = None
    proc_c = None
    log_file_a = None
    log_file_b = None
    log_file_c = None

    url_a = "http://127.0.0.1:5100"
    url_b = "http://127.0.0.1:5101"
    url_c = "http://127.0.0.1:5102"

    passed_checks = 0
    total_checks = 10

    data_dir_a = os.path.join(temp_dir, "data_5100")
    wallet_dir_a = os.path.join(temp_dir, "wallets_5100")
    data_dir_b = os.path.join(temp_dir, "data_5101")
    wallet_dir_b = os.path.join(temp_dir, "wallets_5101")
    data_dir_c = os.path.join(temp_dir, "data_5102")
    wallet_dir_c = os.path.join(temp_dir, "wallets_5102")

    log_path_a = os.path.join(temp_dir, "node_5100.log")
    log_path_b = os.path.join(temp_dir, "node_5101.log")
    log_path_c = os.path.join(temp_dir, "node_5102.log")

    try:
        print("=" * 68)
        print("      MYCOIN 3-NODE AUTOMATED CLUSTER INTEGRATION DEMO")
        print(f"      Temp Cluster Directory: {temp_dir}")
        print("=" * 68)

        # -----------------------------------------------------------------
        # Start the 3 nodes
        # -----------------------------------------------------------------
        print("\nStarting Node A (port 5100), Node B (port 5101), Node C (port 5102)...")
        log_file_a = open(log_path_a, "w", encoding="utf-8")
        log_file_b = open(log_path_b, "w", encoding="utf-8")
        log_file_c = open(log_path_c, "w", encoding="utf-8")

        proc_a = subprocess.Popen(
            [
                sys.executable,
                "node.py",
                "--port", "5100",
                "--host", "127.0.0.1",
                "--public-url", url_a,
                "--data-dir", data_dir_a,
                "--wallet-dir", wallet_dir_a,
                "--peers", url_b, url_c,
            ],
            stdout=log_file_a,
            stderr=subprocess.STDOUT,
        )

        proc_b = subprocess.Popen(
            [
                sys.executable,
                "node.py",
                "--port", "5101",
                "--host", "127.0.0.1",
                "--public-url", url_b,
                "--data-dir", data_dir_b,
                "--wallet-dir", wallet_dir_b,
                "--peers", url_a, url_c,
            ],
            stdout=log_file_b,
            stderr=subprocess.STDOUT,
        )

        proc_c = subprocess.Popen(
            [
                sys.executable,
                "node.py",
                "--port", "5102",
                "--host", "127.0.0.1",
                "--public-url", url_c,
                "--data-dir", data_dir_c,
                "--wallet-dir", wallet_dir_c,
                "--peers", url_a, url_b,
            ],
            stdout=log_file_c,
            stderr=subprocess.STDOUT,
        )

        # Wait for all nodes to become healthy
        if not (wait_for_node(url_a) and wait_for_node(url_b) and wait_for_node(url_c)):
            print("[FAIL] Failed to start all 3 node processes within 20 seconds.")
            return 1
        print("All 3 nodes responded to health check.")

        # -----------------------------------------------------------------
        # Step 1: Peer connection check
        # -----------------------------------------------------------------
        print("\n--- [Step 1] Peer Connection Verification ---")
        deadline = time.time() + 15.0
        step1_ok = False
        while time.time() < deadline:
            try:
                peers_a = set(requests.get(f"{url_a}/nodes", timeout=1).json())
                peers_b = set(requests.get(f"{url_b}/nodes", timeout=1).json())
                peers_c = set(requests.get(f"{url_c}/nodes", timeout=1).json())

                if (
                    {url_b, url_c}.issubset(peers_a)
                    and {url_a, url_c}.issubset(peers_b)
                    and {url_a, url_b}.issubset(peers_c)
                ):
                    step1_ok = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if step1_ok:
            passed_checks += 1
            print("[PASS] All 3 nodes are interconnected with peer links.")
        else:
            print("[FAIL] Peer connections did not establish within 15 seconds.")

        # -----------------------------------------------------------------
        # Step 2: Create wallets for Alice and Bob on Node A
        # -----------------------------------------------------------------
        print("\n--- [Step 2] Create Wallets for Alice and Bob on Node A ---")
        resp_alice = requests.get(f"{url_a}/wallet/new", timeout=2).json()
        resp_bob = requests.get(f"{url_a}/wallet/new", timeout=2).json()

        alice_addr = resp_alice["address"]
        alice_priv = resp_alice["private_key"]
        bob_addr = resp_bob["address"]
        bob_priv = resp_bob["private_key"]

        if alice_addr and alice_priv and bob_addr and bob_priv:
            passed_checks += 1
            print(f"Alice Address: {alice_addr[:12]}...")
            print(f"Bob Address:   {bob_addr[:12]}...")
            print("[PASS] Successfully created wallets for Alice and Bob.")
        else:
            print("[FAIL] Failed to generate wallets for Alice and Bob.")

        # -----------------------------------------------------------------
        # Step 3: Mine on Node A for Alice
        # -----------------------------------------------------------------
        print("\n--- [Step 3] Mine on Node A Crediting Alice ---")
        requests.get(f"{url_a}/mine?miner={alice_addr}", timeout=4)
        bal_alice_a = requests.get(f"{url_a}/balance/{alice_addr}", timeout=2).json()["balance"]

        if bal_alice_a == 50:
            passed_checks += 1
            print(f"Alice balance on Node A: {bal_alice_a} MYC")
            print("[PASS] Alice mined a block on Node A and received 50 MYC.")
        else:
            print(f"[FAIL] Expected Alice balance 50 on Node A, got {bal_alice_a}.")

        # -----------------------------------------------------------------
        # Step 4: Block propagation to Node B and Node C
        # -----------------------------------------------------------------
        print("\n--- [Step 4] Block Propagation Check Across All Nodes ---")
        deadline = time.time() + 20.0
        step4_ok = False
        while time.time() < deadline:
            try:
                chain_a = requests.get(f"{url_a}/chain", timeout=1).json()
                chain_b = requests.get(f"{url_b}/chain", timeout=1).json()
                chain_c = requests.get(f"{url_c}/chain", timeout=1).json()

                if (
                    chain_a["length"] == 2
                    and chain_b["length"] == 2
                    and chain_c["length"] == 2
                    and chain_a["chain"][-1]["hash"] == chain_b["chain"][-1]["hash"] == chain_c["chain"][-1]["hash"]
                ):
                    bal_b = requests.get(f"{url_b}/balance/{alice_addr}", timeout=1).json()["balance"]
                    bal_c = requests.get(f"{url_c}/balance/{alice_addr}", timeout=1).json()["balance"]
                    if bal_b == 50 and bal_c == 50:
                        step4_ok = True
                        break
            except Exception:
                pass
            time.sleep(0.5)

        if step4_ok:
            passed_checks += 1
            print("[PASS] Block 1 propagated to all nodes; Alice balance is 50 MYC on Node B and Node C.")
        else:
            print("[FAIL] Block propagation failed or Alice balance inconsistent.")

        # -----------------------------------------------------------------
        # Step 5: Transaction propagation from Node B
        # -----------------------------------------------------------------
        print("\n--- [Step 5] Transaction Propagation (Alice sends 20 MYC to Bob via Node B) ---")
        tx_resp = requests.post(
            f"{url_b}/demo/send",
            json={
                "private_key": alice_priv,
                "receiver": bob_addr,
                "amount": 20,
                "data": "Cluster demo payment",
            },
            timeout=2,
        )
        if tx_resp.status_code != 201:
            print(f"[FAIL] /demo/send failed with status {tx_resp.status_code}: {tx_resp.text}")
        else:
            deadline = time.time() + 20.0
            step5_ok = False
            while time.time() < deadline:
                try:
                    pend_a = requests.get(f"{url_a}/pending", timeout=1).json()
                    pend_b = requests.get(f"{url_b}/pending", timeout=1).json()
                    pend_c = requests.get(f"{url_c}/pending", timeout=1).json()

                    match_a = any(t["sender"] == alice_addr and t["amount"] == 20 for t in pend_a)
                    match_b = any(t["sender"] == alice_addr and t["amount"] == 20 for t in pend_b)
                    match_c = any(t["sender"] == alice_addr and t["amount"] == 20 for t in pend_c)

                    if match_a and match_b and match_c:
                        step5_ok = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            if step5_ok:
                passed_checks += 1
                print("[PASS] Transaction propagated to mempools on all 3 nodes.")
            else:
                print("[FAIL] Transaction did not propagate to all mempools within 20 seconds.")

        # -----------------------------------------------------------------
        # Step 6: Mine on Node C and verify balances
        # -----------------------------------------------------------------
        print("\n--- [Step 6] Mine on Node C and Verify Confirmed Balances ---")
        node_c_addr = requests.get(f"{url_c}/", timeout=2).json()["address"]
        mine_c_res = requests.get(f"{url_c}/mine", timeout=4)
        if mine_c_res.status_code != 200:
            print(f"[FAIL] Mining on Node C failed with status {mine_c_res.status_code}.")
        else:
            deadline = time.time() + 20.0
            step6_ok = False
            while time.time() < deadline:
                try:
                    c_a = requests.get(f"{url_a}/chain", timeout=1).json()
                    c_b = requests.get(f"{url_b}/chain", timeout=1).json()
                    c_c = requests.get(f"{url_c}/chain", timeout=1).json()

                    p_a = requests.get(f"{url_a}/pending", timeout=1).json()
                    p_b = requests.get(f"{url_b}/pending", timeout=1).json()
                    p_c = requests.get(f"{url_c}/pending", timeout=1).json()

                    if (
                        c_a["length"] == 3 and c_b["length"] == 3 and c_c["length"] == 3
                        and c_a["chain"][-1]["hash"] == c_b["chain"][-1]["hash"] == c_c["chain"][-1]["hash"]
                        and len(p_a) == 0 and len(p_b) == 0 and len(p_c) == 0
                    ):
                        bal_alice_all = [
                            requests.get(f"{u}/balance/{alice_addr}", timeout=1).json()["balance"]
                            for u in [url_a, url_b, url_c]
                        ]
                        bal_bob_all = [
                            requests.get(f"{u}/balance/{bob_addr}", timeout=1).json()["balance"]
                            for u in [url_a, url_b, url_c]
                        ]
                        bal_node_c_all = [
                            requests.get(f"{u}/balance/{node_c_addr}", timeout=1).json()["balance"]
                            for u in [url_a, url_b, url_c]
                        ]

                        if bal_alice_all == [30, 30, 30] and bal_bob_all == [20, 20, 20] and bal_node_c_all == [50, 50, 50]:
                            step6_ok = True
                            break
                except Exception:
                    pass
                time.sleep(0.5)

            if step6_ok:
                passed_checks += 1
                print("[PASS] Block 2 confirmed across all nodes. Balances: Alice=30, Bob=20, Node C=50.")
            else:
                print("[FAIL] Block 2 confirmation or balance checks failed.")

        # -----------------------------------------------------------------
        # Step 7: Tamper test
        # -----------------------------------------------------------------
        print("\n--- [Step 7] Tamper Detection Test on Node A ---")
        chain_a_data = requests.get(f"{url_a}/chain", timeout=2).json()["chain"]
        tampered_block = copy.deepcopy(chain_a_data[-1])
        # Tamper with the non-reward transaction amount
        tampered_block["transactions"][1]["amount"] = 99999

        tamper_res = requests.post(f"{url_a}/blocks/receive", json=tampered_block, timeout=2)
        chain_after_tamper = requests.get(f"{url_a}/chain", timeout=2).json()

        if (
            tamper_res.status_code == 400
            and chain_after_tamper["length"] == 3
            and chain_after_tamper["chain"][-1]["hash"] == chain_a_data[-1]["hash"]
        ):
            passed_checks += 1
            print("[PASS] Tampered block rejected with status 400; chain tip unchanged.")
        else:
            print(f"[FAIL] Tamper test failed (status: {tamper_res.status_code}).")

        # -----------------------------------------------------------------
        # Step 8: Insufficient funds test
        # -----------------------------------------------------------------
        print("\n--- [Step 8] Insufficient Funds Rejection Test ---")
        overspend_res = requests.post(
            f"{url_a}/demo/send",
            json={
                "private_key": bob_priv,
                "receiver": alice_addr,
                "amount": 1000,
            },
            timeout=2,
        )
        if overspend_res.status_code == 400:
            passed_checks += 1
            print("[PASS] Overspending transaction rejected with status 400.")
        else:
            print(f"[FAIL] Expected status 400, got {overspend_res.status_code}.")

        # -----------------------------------------------------------------
        # Step 9: Offline catch-up test
        # -----------------------------------------------------------------
        print("\n--- [Step 9] Offline Node Catch-Up Test ---")
        print("Stopping Node C process...")
        proc_c.terminate()
        try:
            proc_c.wait(timeout=5)
        except Exception:
            proc_c.kill()

        # Mine 2 blocks on Node A with transactions in between
        print("Mining Block #4 on Node A (Alice sends 2 MYC to Bob)...")
        requests.post(
            f"{url_a}/demo/send",
            json={"private_key": alice_priv, "receiver": bob_addr, "amount": 2},
            timeout=2,
        )
        requests.get(f"{url_a}/mine", timeout=4)

        print("Mining Block #5 on Node A (Alice sends 3 MYC to Bob)...")
        requests.post(
            f"{url_a}/demo/send",
            json={"private_key": alice_priv, "receiver": bob_addr, "amount": 3},
            timeout=2,
        )
        requests.get(f"{url_a}/mine", timeout=4)

        chain_a_latest = requests.get(f"{url_a}/chain", timeout=2).json()
        print(f"Node A chain is now at length {chain_a_latest['length']}.")

        print("Restarting Node C...")
        log_file_c.close()
        log_file_c = open(log_path_c, "a", encoding="utf-8")
        proc_c = subprocess.Popen(
            [
                sys.executable,
                "node.py",
                "--port", "5102",
                "--host", "127.0.0.1",
                "--public-url", url_c,
                "--data-dir", data_dir_c,
                "--wallet-dir", wallet_dir_c,
                "--peers", url_a, url_b,
            ],
            stdout=log_file_c,
            stderr=subprocess.STDOUT,
        )

        wait_for_node(url_c, timeout=20.0)

        # Poll until Node C has caught up
        start_catchup = time.time()
        deadline = time.time() + 40.0
        step9_ok = False
        while time.time() < deadline:
            try:
                chain_c_now = requests.get(f"{url_c}/chain", timeout=1).json()
                if (
                    chain_c_now["length"] == chain_a_latest["length"]
                    and chain_c_now["chain"][-1]["hash"] == chain_a_latest["chain"][-1]["hash"]
                ):
                    step9_ok = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

        elapsed_catchup = time.time() - start_catchup

        if step9_ok:
            passed_checks += 1
            print(f"[PASS] Offline Node C caught up to Node A's chain (Length: 5) in {elapsed_catchup:.2f} seconds.")
        else:
            print("[FAIL] Node C failed to catch up to Node A within 40 seconds.")

        # -----------------------------------------------------------------
        # Step 10: Final consistency check across all nodes
        # -----------------------------------------------------------------
        print("\n--- [Step 10] Final Consistency Check Across All 3 Nodes ---")
        chain_a_final = requests.get(f"{url_a}/chain", timeout=2).json()["chain"]
        chain_b_final = requests.get(f"{url_b}/chain", timeout=2).json()["chain"]
        chain_c_final = requests.get(f"{url_c}/chain", timeout=2).json()["chain"]

        bal_alice = [requests.get(f"{u}/balance/{alice_addr}", timeout=1).json()["balance"] for u in [url_a, url_b, url_c]]
        bal_bob = [requests.get(f"{u}/balance/{bob_addr}", timeout=1).json()["balance"] for u in [url_a, url_b, url_c]]
        bal_c_final = [requests.get(f"{u}/balance/{node_c_addr}", timeout=1).json()["balance"] for u in [url_a, url_b, url_c]]

        chains_match = (chain_a_final == chain_b_final == chain_c_final)
        balances_match = (
            len(set(bal_alice)) == 1
            and len(set(bal_bob)) == 1
            and len(set(bal_c_final)) == 1
        )

        if chains_match and balances_match:
            passed_checks += 1
            print(f"Final Balances: Alice={bal_alice[0]}, Bob={bal_bob[0]}, Node C={bal_c_final[0]}")
            print("[PASS] Full ledger and balance consistency verified across all 3 nodes.")
        else:
            print("[FAIL] Inconsistency detected between node chains or balances.")

        # -----------------------------------------------------------------
        # Summary
        # -----------------------------------------------------------------
        print("\n" + "=" * 68)
        print(f"DEMO SUMMARY: {passed_checks}/{total_checks} CHECKS PASSED")
        print("=" * 68)

        return 0 if passed_checks == total_checks else 1

    finally:
        print("\nStopping all cluster node processes...")
        for proc in [proc_a, proc_b, proc_c]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()

        for f in [log_file_a, log_file_b, log_file_c]:
            if f and not f.closed:
                f.close()

        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        print("Cluster cleanup complete.")


if __name__ == "__main__":
    sys.exit(run_demo())
