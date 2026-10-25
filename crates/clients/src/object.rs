//! Raw Client initialization and destruction order over copied native facts.
//! Function pointers, allocations, callbacks and Socket custody remain native.
#[repr(C)]
pub struct ClientsObjectPlan {
    pub action: u32,
    pub stage: u32,
}
/// Operation0 constructor,1 destructor. Facts are observed afresh at each stage.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_object_next(
    operation: u32,
    stage: u32,
    fact: u8,
) -> ClientsObjectPlan {
    let action = match (operation, stage) {
        (0, 0) if fact != 0 => 1, // stream fd class
        (0, 0) => 2,
        (0, 1) => 3,              // native make_socket
        (0, 2) if fact != 0 => 4, // object/buffer defaults
        (0, 2) => 5,              // warn and return
        (0, 3) if fact != 0 => 6, // stream recv, then async decision
        (0, 3) => 7,              // datagram dispatch
        (0, 4) if fact != 0 => 8,
        (0, 4) => 9,
        (0, 5) => 10,              // domain/type and remote address
        (0, 6) => 11,              // protocol defaults
        (1, 0) if fact != 0 => 12, // original native assertion
        (1, 1) if fact == 0 => 13, // close before buffer destruction
        (1, 1) => 16,              // advance
        (1, 2) if fact != 0 => 14,
        (1, 2) => 16,
        (1, 3) if fact != 0 => 15, // detach object then async Socket free
        (1, 3) => 17,              // native synchronous Socket deletion
        _ => 0,
    };
    let next = match (operation, stage, action) {
        (0, 3, 7) => 5,
        (_, _, 0 | 5) => 0,
        _ => stage + 1,
    };
    ClientsObjectPlan {
        action,
        stage: next,
    }
}
