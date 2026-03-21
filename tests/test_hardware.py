"""Hardware detection tests."""

from app.services.hardware import HardwareProfile


def test_hardware_detection():
    """Test that hardware detection returns valid profile."""
    profile = HardwareProfile()

    assert profile.cpu_cores >= 1
    assert profile.ram_gb > 0
    assert profile.gpu_type in ('nvidia_cuda', 'apple_metal', 'intel_igpu', 'amd_rocm', 'none')
    assert profile.tier() in ('high_gpu', 'mid_gpu', 'igpu', 'high_cpu', 'mid_cpu', 'low')


def test_optimal_config():
    """Test that optimal config returns valid settings."""
    profile = HardwareProfile()
    config = profile.optimal_config()

    assert 'providers' in config
    assert 'face_det_size' in config
    assert 'batch_size' in config
    assert 'parallel_workers' in config
    assert config['face_det_size'] >= 320
    assert config['batch_size'] >= 1
    assert config['parallel_workers'] >= 1


def test_hardware_to_dict():
    """Test serialization."""
    profile = HardwareProfile()
    d = profile.to_dict()

    assert 'cpu_cores' in d
    assert 'ram_gb' in d
    assert 'gpu_type' in d
    assert 'tier' in d
    assert 'platform' in d
