//! Initialized symbolic source model only: no foreign calls, pointers, unsafe,
//! allocation, callbacks, failure injection, or object lifetime/destruction.
//! These are handwritten transcriptions, not execution of the product bodies.
#[derive(Clone, Copy, Debug, PartialEq)]
struct State {
    token: u32,
    length: usize,
    capacity: usize,
    offset: usize,
    bytes: [u8; 64],
}
impl State {
    fn initialized(length: usize, capacity: usize) -> Self {
        let mut state = Self { token: 1, length, capacity, offset: 0, bytes: [0; 64] };
        state.bytes[..4].copy_from_slice(b"abcd");
        state
    }
}
fn aligned(value: usize) -> usize { (value + 7) & !7 }
#[derive(Debug, PartialEq)]
struct Requests { values: [usize; 4], used: usize }
impl Requests {
    fn new() -> Self { Self { values: [0; 4], used: 0 } }
    fn record(&mut self, capacity: usize) {
        self.values[self.used] = capacity;
        self.used += 1;
    }
    fn slice(&self) -> &[usize] { &self.values[..self.used] }
}
fn symbolic_success(state: &mut State, capacity: usize, requests: &mut Requests) {
    // Symbolic token change and recorded request, never an actual realloc.
    requests.record(capacity);
    state.token += 1;
    state.capacity = capacity;
}
fn original_append(state: &mut State, input: &[u8], requests: &mut Requests, metadata_effect: bool) {
    let requested = state.length + input.len();
    if requested > state.capacity {
        let capacity = aligned(requested);
        // Model only the allowed initialized field stores of an external effect.
        if metadata_effect { state.length = 1; state.offset = 1; }
        symbolic_success(state, capacity, requests);
    }
    let at = state.length; // Fresh read after the reserve effect.
    state.bytes[at..at + input.len()].copy_from_slice(input);
    state.length += input.len();
}
fn selected_append(state: &mut State, input: &[u8], requests: &mut Requests) {
    let snapshot = *state;
    let end = snapshot.length + input.len();
    let capacity = aligned(end);
    state.length = 1;
    state.offset = 1;
    symbolic_success(state, capacity, requests);
    // edit_string applies to the entry POD, then publish_state writes all fields.
    state.bytes[snapshot.length..end].copy_from_slice(input);
    state.length = end;
    state.offset = snapshot.offset;
}
fn main() {
    let mut original = State::initialized(2, 4);
    let mut selected = original;
    let mut original_requests = Requests::new();
    let mut selected_requests = Requests::new();
    original_append(&mut original, b"XYZ", &mut original_requests, true);
    selected_append(&mut selected, b"XYZ", &mut selected_requests);
    assert_eq!(original_requests.slice(), &[8]);
    assert_eq!(original_requests, selected_requests);
    assert_eq!((original.token, original.length, original.capacity, original.offset), (2, 4, 8, 1));
    assert_eq!((selected.token, selected.length, selected.capacity, selected.offset), (2, 5, 8, 0));
    assert_eq!(&original.bytes[..4], b"aXYZ");
    assert_eq!(&selected.bytes[..5], b"abXYZ");
    println!("APPEND: original len4/off1/aXYZ; selected len5/off0/abXYZ; symbolic request [8] both");

    let mut original = State::initialized(0, 8);
    let mut selected = original;
    let input = *b"abcdefghijklmnopq";
    let mut original_requests = Requests::new();
    let mut selected_requests = Requests::new();
    for _ in 0..3 { original_append(&mut original, &input, &mut original_requests, false); }
    // Selected REPEAT plans the complete final size once before applying bytes.
    let added = input.len() * 3;
    symbolic_success(&mut selected, aligned(added), &mut selected_requests);
    for i in 0..3 { selected.bytes[i * input.len()..(i + 1) * input.len()].copy_from_slice(&input); }
    selected.length = added;
    assert_eq!(original_requests.slice(), &[24, 40, 56]);
    assert_eq!(selected_requests.slice(), &[56]);
    assert_eq!((original.length, original.capacity, original.offset), (51, 56, 0));
    assert_eq!((selected.length, selected.capacity, selected.offset), (51, 56, 0));
    assert_eq!(original.bytes, selected.bytes);
    println!("REPEAT: original requests [24,40,56]; selected [56]; same initialized final bytes/len51/cap56");
    println!("STATIC_MODEL_PASS: two source counterexamples; native behavior was not executed or qualified");
}
