#include <assert.h>
#include <stdio.h>

#include "flow_carousel_model.h"

static void test_drag_offset_is_clamped(void)
{
    assert(flow_carousel_drag_offset(80, 342) == 80);
    assert(flow_carousel_drag_offset(500, 342) == 342);
    assert(flow_carousel_drag_offset(-500, 342) == -342);
}

static void test_small_drag_snaps_back(void)
{
    flow_carousel_release_t result = flow_carousel_release(31, 4, 120, 2, 5, false);
    assert(result.step == 0);
    assert(result.target_offset == 0);
    assert(result.duration_ms == 140);
}

static void test_distance_and_velocity_choose_one_step(void)
{
    flow_carousel_release_t left = flow_carousel_release(-70, 8, -200, 2, 5, false);
    flow_carousel_release_t fling = flow_carousel_release(24, 3, 820, 2, 5, false);
    assert(left.step == 1);
    assert(left.target_offset == -342);
    assert(fling.step == -1);
    assert(fling.target_offset == 342);
}

static void test_vertical_and_energy_bounds_do_not_switch(void)
{
    assert(flow_carousel_release(80, 110, 900, 2, 5, false).step == 0);
    assert(flow_carousel_release(90, 1, 400, 0, 5, false).step == 0);
    assert(flow_carousel_release(-90, 1, -400, 4, 5, false).step == 0);
}

static void test_style_neighbors_wrap(void)
{
    assert(flow_carousel_neighbor(0, -1, 4, true) == 3);
    assert(flow_carousel_neighbor(3, 1, 4, true) == 0);
    assert(flow_carousel_neighbor(2, -1, 5, false) == 1);
}

int main(void)
{
    test_drag_offset_is_clamped();
    test_small_drag_snaps_back();
    test_distance_and_velocity_choose_one_step();
    test_vertical_and_energy_bounds_do_not_switch();
    test_style_neighbors_wrap();
    puts("carousel model tests passed");
    return 0;
}
