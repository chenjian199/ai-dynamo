# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
from pathlib import Path
from typing import List

# Default concurrency levels - can be overridden with CONCURRENCIES environment variable
DEFAULT_CONCURRENCIES: List[int] = [1, 2, 5, 10, 50, 100, 250]


def get_concurrency_levels() -> List[int]:
    """Get concurrency levels from environment variable or use defaults"""
    concurrencies_env = os.getenv("CONCURRENCIES")
    if concurrencies_env:
        try:
            # Parse comma-separated values
            concurrencies = [int(x.strip()) for x in concurrencies_env.split(",")]
            # Validate all are positive integers
            for c in concurrencies:
                if c <= 0:
                    raise ValueError(f"Concurrency level must be positive, got: {c}")
            return sorted(concurrencies)
        except ValueError as e:
            print(f"WARNING: Invalid CONCURRENCIES environment variable: {e}")
            print(f"Using default concurrency levels: {DEFAULT_CONCURRENCIES}")
            return DEFAULT_CONCURRENCIES

    return DEFAULT_CONCURRENCIES


CONCURRENCIES: List[int] = get_concurrency_levels()


def run_genai_perf(
    service_url: str,
    model_name: str,
    isl: int,
    osl: int,
    stddev: int,
    concurrency: int,
    output_dir: Path,
) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    #cj#add
    deployment_model_id = os.environ.get("DEPLOYMENT_MODEL_ID", model_name)
    tokenizer_arg = os.environ.get("TOKENIZER_PATH", model_name)
    #cj#add

    cmd = [
        "genai-perf",
        "profile",
        "-m",
        deployment_model_id,
        #model_name,
        "--endpoint-type",
        "chat",
        "--streaming",
        "-u",
        service_url,
        "--synthetic-input-tokens-mean",
        str(isl),
        "--synthetic-input-tokens-stddev",
        str(stddev),
        "--concurrency",
        str(concurrency),
        "--output-tokens-mean",
        str(osl),
        "--extra-inputs",
        f"max_tokens:{osl}",
        "--extra-inputs",
        f"min_tokens:{osl}",
        "--extra-inputs",
        "ignore_eos:true",
        "--tokenizer",
        tokenizer_arg,
        #model_name,
        "--artifact-dir",
        str(output_dir),
        "--",
        "-vv",
        "--max-threads=300",
    ]
    print(
        f"Running genai-perf with isl {isl}, osl {osl}, concurrency {concurrency}",
        flush=True,
    )

    try:
        gap_process = subprocess.Popen(
            cmd,
            cwd=str(output_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = gap_process.communicate(timeout=300) # 5分钟超时
        if gap_process.returncode == 0:
            print("Genai-perf profiling completed successfully", flush=True)
            if stdout:
                print(stdout)
            return True
        else:
            print(f"Genai-perf failed with error code: {gap_process.returncode}")
            if stderr:
                print(f"stderr: {stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("Genai-perf timed out after 5 minutes", flush=True)
        gap_process.kill()
        gap_process.wait()
        return False
    except Exception as e:
        print(f"Genai-perf failed with exception: {e}", flush=True)
        return False


def run_concurrency_sweep(
    service_url: str, model_name: str, isl: int, osl: int, stddev: int, output_dir: Path
) -> None:
    concurrency_levels = get_concurrency_levels()
    print(
        f"Running concurrency sweep for {model_name} with ISL {isl} and OSL {osl} and standard deviation {stddev}",
        flush=True,
    )
    print(f"Concurrency levels: {concurrency_levels}", flush=True)

    failed_tests = 0
    total_tests = len(concurrency_levels)
    
    for i, c in enumerate(concurrency_levels):
        print(f"Starting concurrency level {c} ({i+1}/{total_tests})", flush=True)
        
        success = run_genai_perf(
            service_url, model_name, isl, osl, stddev, c, output_dir / f"c{c}"
        )
        
        if success:
            print(f"Concurrency {c} test completed successfully", flush=True)
            failed_tests = 0  # reset failed count on success
        else:
            failed_tests += 1
            print(f"Concurrency {c} test failed ({failed_tests} consecutive failures)", flush=True)
            
            # if consecutive failures too many, stop the test
            if failed_tests >= 3:
                print(f"WARNING: {failed_tests} consecutive failures, stopping the test", flush=True)
                print("This usually indicates the system has reached its performance limit", flush=True)
                break
        
        # short break between tests
        # if i < len(concurrency_levels) - 1:
        #     print("Waiting 5 seconds before next test...", flush=True)
        #     import time
        #     time.sleep(5)
    
    print(f"Concurrency sweep completed. Total tests: {total_tests}, Failed tests: {failed_tests}", flush=True)
