idf_component_register(
    SRCS "flow_protocol.c"
    INCLUDE_DIRS "include"
    REQUIRES flow_core espressif__cbor
)
