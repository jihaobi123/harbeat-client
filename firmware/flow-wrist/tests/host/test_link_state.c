#include <assert.h>
#include <stdio.h>

#include "flow_link_state.h"

static void test_connection_progression(void)
{
    flow_link_inputs_t input = {0};
    assert(flow_link_resolve(&input) == FLOW_LINK_ADVERTISING);
    input.connected = true;
    assert(flow_link_resolve(&input) == FLOW_LINK_SECURING);
    input.encrypted = true;
    input.command_subscribed = true;
    assert(flow_link_resolve(&input) == FLOW_LINK_SYNCING_CATALOG);
    input.catalog_received = true;
    assert(flow_link_resolve(&input) == FLOW_LINK_SYNCING_STATE);
    input.state_received = true;
    assert(flow_link_resolve(&input) == FLOW_LINK_READY);
}

static void test_subscription_is_part_of_secure_link(void)
{
    flow_link_inputs_t input = {.connected = true, .encrypted = true};
    assert(flow_link_resolve(&input) == FLOW_LINK_SECURING);
}

static void test_version_mismatch_blocks_ready(void)
{
    flow_link_inputs_t input = {
        .connected = true,
        .encrypted = true,
        .command_subscribed = true,
        .catalog_received = true,
        .state_received = true,
        .version_mismatch = true,
    };
    assert(flow_link_resolve(&input) == FLOW_LINK_VERSION_MISMATCH);
    input.connected = false;
    assert(flow_link_resolve(&input) == FLOW_LINK_ADVERTISING);
}

int main(void)
{
    test_connection_progression();
    test_subscription_is_part_of_secure_link();
    test_version_mismatch_blocks_ready();
    puts("link state tests passed");
    return 0;
}
