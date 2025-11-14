#include <cstdio>
#include <cuda_runtime.h>

int main() {
    int num_gpus;
    cudaError_t err = cudaGetDeviceCount(&num_gpus);
    if (err != cudaSuccess) {
        printf("Error getting device count: %s\n", cudaGetErrorString(err));
        return 1;
    }
    printf("Found %d GPUs\n", num_gpus);

    if (num_gpus < 2) {
        printf("Warning: Need at least 2 GPUs, but only found %d\n", num_gpus);
        return 1;
    }

    // 测试GPU 0和GPU 1之间的P2P
    int canAccess = 0;
    err = cudaDeviceCanAccessPeer(&canAccess, 0, 1);
    if (err != cudaSuccess) {
        printf("Error checking peer access: %s\n", cudaGetErrorString(err));
        return 1;
    }
    printf("GPU 0 can access GPU 1: %s\n", canAccess ? "YES" : "NO");
    
    if (canAccess) {
        // 启用P2P访问
        err = cudaSetDevice(0);
        if (err != cudaSuccess) {
            printf("Error setting device 0: %s\n", cudaGetErrorString(err));
            return 1;
        }
        err = cudaDeviceEnablePeerAccess(1, 0);
        if (err != cudaSuccess && err != cudaErrorPeerAccessAlreadyEnabled) {
            printf("Error enabling peer access: %s\n", cudaGetErrorString(err));
            return 1;
        }
        
        // 分配内存
        float *d0, *d1;
        size_t size = 10ULL * 1024 * 1024 * 1024; // 10GB (使用ULL避免整数溢出)
        
        err = cudaSetDevice(0);
        if (err != cudaSuccess) {
            printf("Error setting device 0: %s\n", cudaGetErrorString(err));
            return 1;
        }
        err = cudaMalloc(&d0, size);
        if (err != cudaSuccess) {
            printf("Error allocating memory on device 0: %s\n", cudaGetErrorString(err));
            return 1;
        }
        
        err = cudaSetDevice(1);
        if (err != cudaSuccess) {
            printf("Error setting device 1: %s\n", cudaGetErrorString(err));
            cudaFree(d0);
            return 1;
        }
        err = cudaMalloc(&d1, size);
        if (err != cudaSuccess) {
            printf("Error allocating memory on device 1: %s\n", cudaGetErrorString(err));
            cudaFree(d0);
            return 1;
        }
        
        // 测试拷贝性能
        err = cudaSetDevice(0);
        if (err != cudaSuccess) {
            printf("Error setting device 0: %s\n", cudaGetErrorString(err));
            cudaFree(d0);
            cudaFree(d1);
            return 1;
        }
        cudaEvent_t start, stop;
        cudaEventCreate(&start);
        cudaEventCreate(&stop);
        
        cudaEventRecord(start);
        for (int i = 0; i < 10; i++) {
            err = cudaMemcpyPeer(d1, 1, d0, 0, size);
            if (err != cudaSuccess) {
                printf("Error in memcpy peer: %s\n", cudaGetErrorString(err));
                cudaFree(d0);
                cudaFree(d1);
                return 1;
            }
        }
        cudaEventRecord(stop);
        cudaEventSynchronize(stop);
        
        float ms;
        cudaEventElapsedTime(&ms, start, stop);
        // 计算单向带宽：总传输数据量 / 时间
        // size * 10 是10次传输的总数据量（字节）
        // ms * 1e-3 将毫秒转换为秒（1毫秒 = 0.001秒）
        // 除以 1e9 将字节转换为 GB（1 GB = 10^9 字节）
        float bandwidth = (size * 10) / (ms * 1e-3) / 1e9; // GB/s
        
        printf("P2P Bandwidth (GPU 0 -> GPU 1): %.2f GB/s\n", bandwidth);
        
        cudaFree(d0);
        cudaFree(d1);
    }
    
    return 0;
}