<?php
// Direct positive Rust metadata ABI in the actual selected extension. No parser,
// Context/Server/Port objects, sockets, user callbacks or failure/lifetime probes.
$ffi = FFI::cdef(<<<'C'
typedef unsigned char uint8_t;
typedef unsigned int uint32_t;
typedef struct SwrWrapperRequest SwrWrapperRequest;
typedef struct { const uint8_t *data; size_t len; } SwrWrapperSpan;
typedef struct { SwrWrapperSpan header, form, input, body; uint32_t flags; } SwrWrapperView;
SwrWrapperRequest *swr_v1_wrappers_request_new(void);
void swr_v1_wrappers_request_free(SwrWrapperRequest *);
int swr_v1_wrappers_disposition(SwrWrapperRequest *, const uint8_t *, size_t);
int swr_v1_wrappers_request_view(const SwrWrapperRequest *, SwrWrapperView *);
C, $argv[1]);
$cases = [
    ['name=a', 'a', 'oldinput'],
    ['filename=b', 'oldform', 'b'],
    ['name', '', 'oldinput'],
    ['filename', 'oldform', ''],
    ['name=first;name=last', 'last', 'oldinput'],
    ['filename=one;filename=two;name=z', 'oldform', 'two'],
    ['filename=;name=x', 'oldform', ''],
    ['NAME=z;name=x', 'x', 'oldinput'],
    ['name =ignored;name=real', 'real', 'oldinput'],
    [' name=  x ', '  x ', 'oldinput'],
    ['name="quoted"', '"quoted"', 'oldinput'],
    ['name=x=y', 'x=y', 'oldinput'],
    ["name=x\0;filename=y", 'x', 'oldinput'],
    ['filename="";name=ignored', 'oldform', '""'],
    ["something; name=x;;\tfilename=y", 'oldform', 'y'],
    [' =bad; name=ok', 'ok', 'oldinput'],
    ["name=before; \r\n name=after", 'after', 'oldinput'],
    ['filename=x;filename', 'oldform', ''],
    ['name=a;filename =not-special', 'a', 'oldinput'],
];
$checks = 0;
for ($round = 0; $round < 64; $round++) {
    foreach ($cases as [$wire, $form, $input]) {
        $state = $ffi->swr_v1_wrappers_request_new();
        if (FFI::isNull($state)) throw new RuntimeException('Request allocation failed');
        try {
            foreach (['name=oldform', 'filename=oldinput', $wire] as $data) {
                $buffer = $ffi->new('uint8_t[' . strlen($data) . ']');
                FFI::memcpy($buffer, $data, strlen($data));
                if ($ffi->swr_v1_wrappers_disposition($state, $buffer, strlen($data)) !== 0) {
                    throw new RuntimeException('Defined ordinary disposition rejected');
                }
            }
            $view = $ffi->new('SwrWrapperView');
            if ($ffi->swr_v1_wrappers_request_view($state, FFI::addr($view)) !== 0) {
                throw new RuntimeException('Request view failed');
            }
            $actualForm = $view->form->len ? FFI::string($ffi->cast('char *', $view->form->data), $view->form->len) : '';
            $actualInput = $view->input->len ? FFI::string($ffi->cast('char *', $view->input->data), $view->input->len) : '';
            if ($actualForm !== $form || $actualInput !== $input || $view->flags !== 0 || $view->header->len !== 0 || $view->body->len !== 0) {
                throw new RuntimeException('Disposition metadata mismatch');
            }
            $checks++;
        } finally {
            $ffi->swr_v1_wrappers_request_free($state);
        }
    }
}
echo json_encode(['checks' => $checks, 'cases' => count($cases), 'rounds' => 64, 'php' => PHP_VERSION,
    'zts' => PHP_ZTS, 'swoole' => phpversion('swoole'), 'ffi' => phpversion('FFI'),
    'parser_or_native_Context_executed' => false, 'passed' => true], JSON_THROW_ON_ERROR), "\n";
