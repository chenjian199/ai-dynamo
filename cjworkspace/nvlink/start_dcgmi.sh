export LOG_DIR="log"
mkdir -p "$LOG_DIR"
dcgmi dmon -i 0,1,2,3,4,5,6,7 -e 203,204,449,1009,1010,1011,1012 -d 500 2>&1 | tee "$LOG_DIR/dcgmi_monitor.log" 2>&1 
echo "dcgmi monitor started, log file: $LOG_DIR/dcgmi_monitor.log"