"""Hardware detection and adaptive engine configuration."""

import logging
import platform
import struct
import os

logger = logging.getLogger(__name__)


class HardwareProfile:
    """Detect and profile system hardware capabilities."""

    def __init__(self):
        self.cpu_cores = self._get_cpu_cores()
        self.cpu_freq_ghz = self._get_cpu_freq()
        self.ram_gb = self._get_ram()
        self.gpu_type = 'none'
        self.gpu_vram_gb = 0.0
        self.gpu_name = 'None'
        self.platform = platform.system().lower()
        self.arch = platform.machine().lower()

        self._detect_gpu()

    def _get_cpu_cores(self):
        try:
            import psutil
            return psutil.cpu_count(logical=True) or os.cpu_count() or 2
        except ImportError:
            return os.cpu_count() or 2

    def _get_cpu_freq(self):
        try:
            import psutil
            freq = psutil.cpu_freq()
            return round(freq.current / 1000, 2) if freq else 2.0
        except Exception:
            return 2.0

    def _get_ram(self):
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except ImportError:
            return 4.0

    def _detect_gpu(self):
        """Detect GPU type in priority order."""
        try:
            import onnxruntime as ort
            available = ort.get_available_providers()
        except ImportError:
            logger.info('onnxruntime not installed, skipping GPU detection')
            return

        # 1. NVIDIA CUDA
        if 'CUDAExecutionProvider' in available:
            self.gpu_type = 'nvidia_cuda'
            self.gpu_name = self._get_nvidia_name()
            self.gpu_vram_gb = self._get_nvidia_vram()
            logger.info(f'GPU detected: NVIDIA {self.gpu_name} ({self.gpu_vram_gb}GB)')
            return

        # 2. Apple Silicon (Metal/CoreML)
        if self.platform == 'darwin' and self.arch in ('arm64', 'aarch64'):
            if 'CoreMLExecutionProvider' in available:
                self.gpu_type = 'apple_metal'
                self.gpu_name = 'Apple Silicon'
                self.gpu_vram_gb = self.ram_gb * 0.5
                logger.info(f'GPU detected: Apple Silicon (shared {self.gpu_vram_gb}GB)')
                return

        # 3. Intel OpenVINO
        if 'OpenVINOExecutionProvider' in available:
            self.gpu_type = 'intel_igpu'
            self.gpu_name = 'Intel Integrated'
            self.gpu_vram_gb = 1.5
            logger.info(f'GPU detected: Intel iGPU (OpenVINO)')
            return

        # 4. Check for AMD ROCm (Linux)
        if self.platform == 'linux' and os.path.exists('/opt/rocm'):
            self.gpu_type = 'amd_rocm'
            self.gpu_name = 'AMD GPU (ROCm)'
            self.gpu_vram_gb = 4.0
            logger.info(f'GPU detected: AMD ROCm')
            return

        # 5. Fallback: CPU
        logger.info(f'No GPU detected, using CPU ({self.cpu_cores} cores, {self.ram_gb}GB RAM)')

    def _get_nvidia_name(self):
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                                    capture_output=True, text=True, timeout=5)
            return result.stdout.strip().split('\n')[0] if result.returncode == 0 else 'NVIDIA GPU'
        except Exception:
            return 'NVIDIA GPU'

    def _get_nvidia_vram(self):
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                mb = int(result.stdout.strip().split('\n')[0])
                return round(mb / 1024, 1)
        except Exception:
            pass
        return 4.0

    def tier(self) -> str:
        """Classify hardware into tiers."""
        if self.gpu_type in ('nvidia_cuda', 'apple_metal') and self.gpu_vram_gb >= 6:
            return 'high_gpu'
        elif self.gpu_type in ('nvidia_cuda', 'apple_metal') and self.gpu_vram_gb >= 2:
            return 'mid_gpu'
        elif self.gpu_type == 'intel_igpu':
            return 'igpu'
        elif self.cpu_cores >= 8 and self.ram_gb >= 8:
            return 'high_cpu'
        elif self.cpu_cores >= 4 and self.ram_gb >= 4:
            return 'mid_cpu'
        else:
            return 'low'

    def optimal_config(self) -> dict:
        """Return optimal engine configuration based on hardware."""
        tier = self.tier()

        configs = {
            'high_gpu': {
                'providers': self._gpu_providers(),
                'face_det_size': 640,
                'batch_size': 16,
                'parallel_workers': 4,
                'recognition_threads': 2,
                'frame_skip': 1,
                'jpeg_quality': 90,
            },
            'mid_gpu': {
                'providers': self._gpu_providers(),
                'face_det_size': 480,
                'batch_size': 4,
                'parallel_workers': 2,
                'recognition_threads': 1,
                'frame_skip': 1,
                'jpeg_quality': 85,
            },
            'igpu': {
                'providers': self._igpu_providers(),
                'face_det_size': 480,
                'batch_size': 2,
                'parallel_workers': 2,
                'recognition_threads': 1,
                'frame_skip': 2,
                'jpeg_quality': 80,
            },
            'high_cpu': {
                'providers': self._cpu_providers(),
                'face_det_size': 480,
                'batch_size': 4,
                'parallel_workers': max(2, self.cpu_cores // 2),
                'recognition_threads': max(1, self.cpu_cores // 2),
                'frame_skip': 2,
                'jpeg_quality': 80,
            },
            'mid_cpu': {
                'providers': self._cpu_providers(),
                'face_det_size': 320,
                'batch_size': 2,
                'parallel_workers': 2,
                'recognition_threads': 1,
                'frame_skip': 3,
                'jpeg_quality': 75,
            },
            'low': {
                'providers': self._cpu_providers(),
                'face_det_size': 320,
                'batch_size': 1,
                'parallel_workers': 1,
                'recognition_threads': 1,
                'frame_skip': 4,
                'jpeg_quality': 70,
            },
        }

        cfg = configs.get(tier, configs['low'])
        cfg['tier'] = tier
        cfg['gpu_type'] = self.gpu_type
        logger.info(f'Hardware tier: {tier} | Config: det_size={cfg["face_det_size"]}, '
                     f'batch={cfg["batch_size"]}, workers={cfg["parallel_workers"]}')
        return cfg

    def _gpu_providers(self):
        if self.gpu_type == 'nvidia_cuda':
            return [
                ('CUDAExecutionProvider', {
                    'device_id': 0,
                    'arena_extend_strategy': 'kSameAsRequested',
                    'gpu_mem_limit': int(self.gpu_vram_gb * 0.7 * 1024 ** 3),
                    'cudnn_conv_algo_search': 'HEURISTIC',
                }),
                'CPUExecutionProvider',
            ]
        elif self.gpu_type == 'apple_metal':
            return ['CoreMLExecutionProvider', 'CPUExecutionProvider']
        return self._cpu_providers()

    def _igpu_providers(self):
        return [
            ('OpenVINOExecutionProvider', {
                'device_type': 'GPU_FP16' if self.gpu_vram_gb > 1 else 'CPU_FP32',
            }),
            'CPUExecutionProvider',
        ]

    def _cpu_providers(self):
        threads = max(1, self.cpu_cores - 1)
        return [
            ('CPUExecutionProvider', {
                'intra_op_num_threads': threads,
                'inter_op_num_threads': max(1, threads // 2),
            }),
        ]

    def to_dict(self):
        return {
            'cpu_cores': self.cpu_cores,
            'cpu_freq_ghz': self.cpu_freq_ghz,
            'ram_gb': self.ram_gb,
            'gpu_type': self.gpu_type,
            'gpu_name': self.gpu_name,
            'gpu_vram_gb': self.gpu_vram_gb,
            'platform': self.platform,
            'arch': self.arch,
            'tier': self.tier(),
        }


# Singleton
_profile = None


def get_hardware_profile() -> HardwareProfile:
    global _profile
    if _profile is None:
        _profile = HardwareProfile()
    return _profile
