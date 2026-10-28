#include <cassert>
#include <cmath>
#include <climits>
#include <cstring>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <initializer_list>
#include "swoole_rs_phpcollections.h"
using zend_long = intptr_t;
struct Columns { size_t n; size_t size() const { return n; } };
static bool column_cursor_failed=false;
static unsigned cursor_opens=0,cursor_errors=0;
struct Table {
    size_t n; Columns *column_list;
    size_t count() const { return n; }
    struct Cursor { size_t n; size_t count() const { return n; } bool failed() const { return column_cursor_failed; } };
    Cursor columns() const { ++cursor_opens;return {column_list->size()}; }
};
using TableV2=Table;
static void zend_throw_error(void *,const char *) { ++cursor_errors; }
#define COUNT_NORMAL 0
#define RETURN_LONG(value) return size_t(value)
#define RETURN_FALSE return size_t(0)
static size_t native_count(Table *table,zend_long mode) {
#include "native-count.inc"
}
static size_t selected_count(Table *table,zend_long mode) {
#include "selected-count.inc"
}
int main() {
    size_t checks=0;
    for (size_t n : {size_t(0),size_t(1),size_t(63),SIZE_MAX}) {
        for (size_t cols : {size_t(0),size_t(1),size_t(7),SIZE_MAX}) {
            Columns columns{cols}; Table table{n,&columns};
            for (intptr_t mode : {INTPTR_MIN,intptr_t(-1),intptr_t(0),intptr_t(1),INTPTR_MAX}) {
                assert(native_count(&table,mode)==selected_count(&table,mode)); ++checks;
            }
        }
    }
    for (int64_t kind=-1024;kind<=1024;++kind) {
        assert(swr_v1_phpcollections_kind(kind)==(kind>=1 && kind<=3?kind:0)); ++checks;
        for (int64_t n : {INT64_MIN,int64_t(-1),int64_t(0),int64_t(1),INT64_MAX}) {
            assert(bool(swr_v1_phpcollections_string_invalid(kind,n))==(kind==3 && n<1)); ++checks;
        }
    }
    for(size_t n=0;n<4096;++n) {
        for(size_t limit=0;limit<256;++limit) {
            assert(bool(swr_v1_phpcollections_key_warning(n,limit))==(n>=limit)); ++checks;
        }
    }
    for(uint8_t row=0;row<2;++row) for(uint8_t field=0;field<2;++field) {
        assert(swr_v1_phpcollections_get_action(row,field)==(row?(field?1:2):0));
        assert(bool(swr_v1_phpcollections_clear_cell(row,field))==(!row || field)); checks+=2;
    }
    for(double value:{-1e308,-1.5,-0.0,0.0,1.5,1e308,double(INFINITY),double(-INFINITY),double(NAN)}) {
        for(double amount:{-1e308,-1.5,-0.0,0.0,1.5,1e308,double(INFINITY),double(-INFINITY),double(NAN)}) {
            for(uint8_t subtract:{uint8_t(0),uint8_t(1)}) {
                const double native=subtract?value-amount:value+amount;
                const double selected=swr_v1_phpcollections_float_update(value,amount,subtract);
                assert((std::isnan(native) && std::isnan(selected)) || std::memcmp(&native,&selected,sizeof(double))==0);
                ++checks;
            }
        }
    }
    for(long value:{LONG_MIN,-123L,-1L,0L,1L,123L,LONG_MAX}) {
        for(long amount:{LONG_MIN,-123L,-1L,0L,1L,123L,LONG_MAX}) {
            for(uint8_t subtract:{uint8_t(0),uint8_t(1)}) {
                long expected=0, actual=789;
                const bool overflow=subtract?__builtin_sub_overflow(value,amount,&expected):__builtin_add_overflow(value,amount,&expected);
                const bool accepted=swr_v1_phpcollections_integer_update(value,amount,subtract,&actual);
                assert(accepted==!overflow);
                assert(accepted?actual==expected:actual==789);
                ++checks;
            }
        }
    }
    cursor_opens=cursor_errors=0;Columns failed_columns{7};Table failed_table{3,&failed_columns};column_cursor_failed=true;
    assert(selected_count(&failed_table,0)==3 && cursor_opens==0 && cursor_errors==0);
    assert(selected_count(&failed_table,1)==0 && cursor_opens==1 && cursor_errors==1);
    column_cursor_failed=false;
    std::printf("{\"checks\":%zu,\"actual_body_checks\":80,\"selected_count_cursor_error_checks\":2}\n",checks);
}
