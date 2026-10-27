//! Copied-fact sequencing for the native PHP resolver cluster consumer.
//! Context/registry, zvals, user callbacks and every destructor stay native.
#[repr(C)]
pub struct ResolverPlan {
    pub action: u32,
    pub stage: u32,
}
/// Stage-local facts only: private context; retval object/string; count==0;
/// retval array; host valid string; `with_port`; port present. Native effects run
/// after return and facts are refreshed only at the original observation point.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_resolver_next(stage: u32, facts: u32) -> ResolverPlan {
    let (action, stage) = match stage {
        0 if facts != 0 => (2, 3), // count existing cluster
        0 => (1, 1),               // lookup
        1 if facts == 1 => (3, 2), // publish object cluster
        1 if facts == 2 => (4, 0), // terminal string and flags
        1 => (5, 0),               // terminal empty and flags
        2 => (7, 4),               // pop cluster
        3 if facts != 0 => (6, 0), // destroy empty cluster, lookup afresh
        3 => (7, 4),
        4 if facts != 0 => (8, 5), // find host after array result
        4 => (14, 0),
        5 if facts != 0 => (9, 6), // copy host after validation
        5 => (14, 0),
        6 if facts != 0 => (10, 7), // append ':' then find port
        6 => (12, 9),               // dtor successful array result
        7 if facts != 0 => (11, 8), // append native long port
        7 => (14, 0),
        8 => (12, 9),
        9 => (13, 0), // return copied result after dtor
        _ => (14, 0),
    };
    ResolverPlan { action, stage }
}
