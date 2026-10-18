from __future__ import annotations

from easy_ride.gpx.elevation import (
    compute_ascent_descent,
    compute_gradients,
    smooth_elevation,
)


class TestSmoothElevation:
    def test_empty(self):
        assert smooth_elevation([]) == []

    def test_single_value(self):
        assert smooth_elevation([100.0]) == [100.0]

    def test_flat_unchanged(self):
        elev = [100.0, 100.0, 100.0, 100.0, 100.0]
        result = smooth_elevation(elev, window=3)
        assert result == elev

    def test_smoothing_reduces_spikes(self):
        elev = [100.0, 100.0, 200.0, 100.0, 100.0]
        result = smooth_elevation(elev, window=3)
        assert result[2] < 200.0  # spike reduced
        assert result[2] > 100.0  # but still elevated

    def test_window_1_returns_original(self):
        elev = [10.0, 20.0, 30.0]
        result = smooth_elevation(elev, window=1)
        assert result == elev

    def test_length_preserved(self):
        elev = [i * 10.0 for i in range(20)]
        result = smooth_elevation(elev, window=5)
        assert len(result) == len(elev)


class TestComputeGradients:
    def test_empty(self):
        assert compute_gradients([], []) == []

    def test_flat(self):
        dists = [0.0, 100.0, 200.0]
        elev = [100.0, 100.0, 100.0]
        grads = compute_gradients(dists, elev)
        assert all(g == 0.0 for g in grads)

    def test_uphill_10_percent(self):
        dists = [0.0, 100.0]
        elev = [0.0, 10.0]
        grads = compute_gradients(dists, elev)
        assert grads[0] == 0.0
        assert abs(grads[1] - 10.0) < 0.01

    def test_downhill(self):
        dists = [0.0, 100.0]
        elev = [10.0, 0.0]
        grads = compute_gradients(dists, elev)
        assert grads[1] < 0

    def test_close_points_carry_forward(self):
        dists = [0.0, 100.0, 100.5]  # third point very close
        elev = [0.0, 10.0, 10.5]
        grads = compute_gradients(dists, elev, min_distance=1.0)
        assert grads[2] == grads[1]  # carried forward

    def test_first_gradient_is_zero(self):
        dists = [0.0, 50.0, 100.0]
        elev = [0.0, 5.0, 10.0]
        assert compute_gradients(dists, elev)[0] == 0.0


class TestAscentDescent:
    def test_flat(self):
        ascent, descent = compute_ascent_descent([100.0, 100.0, 100.0])
        assert ascent == 0.0
        assert descent == 0.0

    def test_uphill_only(self):
        ascent, descent = compute_ascent_descent([0.0, 10.0, 30.0])
        assert ascent == 30.0
        assert descent == 0.0

    def test_downhill_only(self):
        ascent, descent = compute_ascent_descent([30.0, 20.0, 0.0])
        assert ascent == 0.0
        assert descent == 30.0

    def test_mixed(self):
        ascent, descent = compute_ascent_descent([0.0, 20.0, 10.0, 25.0])
        assert ascent == 35.0  # 20 + 15
        assert descent == 10.0
