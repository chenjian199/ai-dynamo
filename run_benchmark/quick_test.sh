#!/usr/bin/env bash

set -euo pipefail

#=====configuration=====
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="${SCRIPT_DIR}/run.sh"

#=====log related=====
log() { echo "[$(date '+%F %T')] $*"; }

#=====main function=====
main() {
    # custom configuration sequence
    local configs=("2" "3" "7" "8" "9" "10")
    
    log "quick test: running configurations: ${configs[*]}"
    
    # check if run.sh exists
    if [[ ! -f "$RUN_SCRIPT" ]]; then
        log "ERROR: run.sh not found at $RUN_SCRIPT"
        exit 1
    fi
    
    # make run.sh executable
   #chmod +x "$RUN_SCRIPT"
    
    # run each configuration
    for i in "${configs[@]}"; do
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
        if [[ "$i" != "${configs[-1]}" ]]; then
            log "waiting 10 seconds before next configuration..."
            sleep 10
        fi
    done
    
    log "quick test completed"
}

#=====run main function=====
main "$@"
