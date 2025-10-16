#!/usr/bin/env bash

set -euo pipefail

#=====configuration=====
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="${SCRIPT_DIR}/run.sh"

#=====log related=====
log() { echo "[$(date '+%F %T')] $*"; }

#=====main function=====
main() {
    local start_config="${1:-1}"
    local end_config="${2:-10}"
    
    log "quick test: running configurations $start_config to $end_config"
    
    # check if run.sh exists
    if [[ ! -f "$RUN_SCRIPT" ]]; then
        log "ERROR: run.sh not found at $RUN_SCRIPT"
        exit 1
    fi
    
    # make run.sh executable
    chmod +x "$RUN_SCRIPT"
    
    # run each configuration
    for i in $(seq $start_config $end_config); do
        log "=========================================="
        log "running configuration $i"
        log "=========================================="
        
        # run the script with automatic input (echo the number)
        if echo "$i" | timeout 1800 "$RUN_SCRIPT"; then
            log "configuration $i completed successfully"
        else
            local exit_code=$?
            log "configuration $i failed with exit code: $exit_code"
        fi
        
        # wait between configurations
        if [[ $i -lt $end_config ]]; then
            log "waiting 10 seconds before next configuration..."
            sleep 10
        fi
    done
    
    log "quick test completed"
}

#=====run main function=====
main "$@"
