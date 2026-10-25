// Full pinned/selected table arithmetic facades over native effect doubles.
#include <array>
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <string>
#include <utility>
#include <vector>
#include "swoole_rs_phpcollections.h"
struct zval { int kind=0; long integer=0; double floating=0; std::string text; std::vector<std::string> array; };
using TableStringLength=uint32_t;
struct zend_string { std::string value; };
static std::string string_value("v\0value",7);
struct Execute {};
static std::vector<std::string> trace;
static bool parse_ok, have_row, have_column, new_row, have_amount;
static zval amount;
struct TableColumn {
    enum Type { TYPE_INT=1, TYPE_FLOAT=2, TYPE_STRING=3 };
    Type type=TYPE_INT;
    size_t index=0;
    std::string name;
};
struct TableRow {
    std::array<unsigned char,16> bytes{};
    unsigned char *data=bytes.data();
    void get_value(const TableColumn *,char **value,TableStringLength *length) {
        trace.push_back("read-string");*value=string_value.data();*length=string_value.size();
    }
    void get_value(const TableColumn *,double *value) { trace.push_back("read-double");std::memcpy(value,data,sizeof(*value)); }
    void get_value(const TableColumn *,long *value) { trace.push_back("read-long");std::memcpy(value,data,sizeof(*value)); }
    void unlock() { trace.push_back("unlock"); }
    void set_value(const TableColumn *column,void *value,size_t) {
        trace.push_back("write");
        std::memcpy(data,value,column->type==TableColumn::TYPE_FLOAT?sizeof(double):sizeof(long));
    }
};
static TableRow row, lock_row;
static TableColumn column;
#define SW_TABLE_FLAG_NEW_ROW 1
static int cursor_failure_after=-1;
// Scripted native effects only: this fixture vector is not production storage.
struct Table {
    std::vector<TableColumn *> *column_list=nullptr;
    struct Cursor {
        const std::vector<TableColumn *> *source;
        size_t offset=0;
        bool invalid=false;
        const TableColumn *next() {
            if(cursor_failure_after>=0 && offset>=size_t(cursor_failure_after)) { invalid=true;return nullptr; }
            return offset==source->size()?nullptr:(*source)[offset++];
        }
        bool failed() const { return invalid; }
    };
    Cursor columns() const { return {column_list}; }
    TableRow *set(const char *key,size_t length,TableRow **lock,int *flags) {
        trace.push_back("set:"+std::string(key,length));*lock=&lock_row;*flags=new_row?SW_TABLE_FLAG_NEW_ROW:0;
        return have_row?&row:nullptr;
    }
    TableColumn *get_column(std::string name) { trace.push_back("column:"+name);return have_column?&column:nullptr; }
    void clear_row(TableRow *value) { trace.push_back("clear");value->bytes.fill(0); }
};
// Scripted descriptor adapter over the SAME fixture vector, not real Rust storage.
struct TableV2 : Table {
    struct Column {
        TableColumn *value=nullptr;
        int copied_kind=0;
        size_t copied_index=0;
        Column(TableColumn *source=nullptr):value(source),copied_kind(source?source->type:0),copied_index(source?source->index:0) {}
        bool valid() const { return value!=nullptr; }
        bool failed() const { return false; }
        int kind() const { return copied_kind; }
        size_t index() const { return copied_index; }
        size_t name_length() const { return value->name.size(); }
        bool copy_name(char *output,size_t capacity) const {
            if(!value || capacity<name_length())return false;
            if(name_length())std::memcpy(output,value->name.data(),name_length());
            return true;
        }
        bool get_value(TableRow *row,long *out) const { row->get_value(value,out);return true; }
        bool get_value(TableRow *row,double *out) const { row->get_value(value,out);return true; }
        bool get_value(TableRow *row,char **out,TableStringLength *length) const { row->get_value(value,out,length);return true; }
        bool set_value(TableRow *row,const void *input,size_t length) const { row->set_value(value,const_cast<void *>(input),length);return true; }
    };
    struct Cursor {
        Table::Cursor source;
        bool next(Column &out) { out=Column{const_cast<TableColumn *>(source.next())};return out.valid(); }
        bool failed() const { return source.failed(); }
    };
    Cursor columns() const { return {Table::columns()}; }
    Column get_column(std::string name) { return {Table::get_column(std::move(name))}; }
};
static TableV2 table;
static TableV2 *table_get_and_check_ptr2(Execute *) { trace.push_back("table");return &table; }
static int zend_parse_parameters(int,const char *,char **key,size_t *keylen,char **field,size_t *fieldlen,zval **change) {
    trace.push_back("parse");static char k[]="key\0suffix",f[]="field\0suffix";
    *key=k;*keylen=sizeof(k)-1;*field=f;*fieldlen=sizeof(f)-1;*change=have_amount?&amount:nullptr;
    return parse_ok?0:-1;
}
static double zval_get_double(zval *value) { trace.push_back("convert-double");return value->floating; }
static long zval_get_long(zval *value) { trace.push_back("convert-long");return value->integer; }
static void zend_throw_error(void *,const char *) { trace.push_back("column-error"); }
static void warning(int,const char *format,...) {
    char output[256];va_list args;va_start(args,format);std::vsnprintf(output,sizeof(output),format,args);va_end(args);
    trace.push_back("warning:"+std::string(output));
}
#define FAILURE -1
#define E_WARNING 2
#define INTERNAL_FUNCTION_PARAMETERS Execute *execute_data,zval *return_value
#define INTERNAL_FUNCTION_PARAM_PASSTHRU execute_data,return_value
#define PHP_METHOD(cls,name) void name(INTERNAL_FUNCTION_PARAMETERS)
#define ZEND_THIS execute_data
#define ZEND_NUM_ARGS() 0
#define php_swoole_fatal_error(...) warning(__VA_ARGS__)
#define RETURN_FALSE do { trace.push_back("false");return_value->kind=1;return_value->integer=0;return; } while(0)
#define RETVAL_DOUBLE(value) do { trace.push_back("return-double");return_value->kind=3;return_value->floating=value; } while(0)
#define RETVAL_LONG(value) do { trace.push_back("return-long");return_value->kind=2;return_value->integer=value; } while(0)

#define ZSTR_VAL(p) ((p)->value.data())
#define ZSTR_LEN(p) ((p)->value.size())
#define ZVAL_FALSE(p) do { trace.push_back("zfalse");(p)->kind=1;(p)->integer=0; } while(0)
#define ZVAL_STRINGL(p,v,n) do { trace.push_back("zstring");(p)->kind=4;(p)->text=std::string(v,n); } while(0)
#define ZVAL_DOUBLE(p,v) do { trace.push_back("zdouble");(p)->kind=3;(p)->floating=v; } while(0)
#define ZVAL_LONG(p,v) do { trace.push_back("zlong");(p)->kind=2;(p)->integer=v; } while(0)
static void array_init(zval *value) { trace.push_back("array");value->kind=5;value->array.clear(); }
static void add_assoc_stringl_ex(zval *array,const char *key,size_t length,char *value,size_t size) {
    trace.push_back("assoc-string");array->array.push_back("string:"+std::string(key,length)+":"+std::string(value,size));
}
static void add_assoc_double_ex(zval *array,const char *key,size_t length,double value) {
    trace.push_back("assoc-double");array->array.push_back("double:"+std::string(key,length)+":"+std::to_string(value));
}
static void add_assoc_long_ex(zval *array,const char *key,size_t length,long value) {
    trace.push_back("assoc-long");array->array.push_back("long:"+std::string(key,length)+":"+std::to_string(value));
}
namespace original {
#include "native-arithmetic.inc"
}
namespace selected {
#include "selected-arithmetic.inc"
}
struct Observation { std::vector<std::string> events; std::array<unsigned char,16> bytes; zval result; };
static Observation run(void(*method)(Execute *,zval *),int type) {
    trace.clear();row.bytes.fill(0);column.type=static_cast<TableColumn::Type>(type);
    long integer=7;double floating=4.5;
    std::memcpy(row.data,type==TableColumn::TYPE_FLOAT?static_cast<void *>(&floating):static_cast<void *>(&integer),type==TableColumn::TYPE_FLOAT?sizeof(double):sizeof(long));
    Execute execute;zval result;method(&execute,&result);return {trace,row.bytes,result};
}
int main() {
    size_t checks=0;
    for(bool parse:{false,true}) for(bool exists:{false,true}) for(bool field:{false,true})
    for(bool fresh:{false,true}) for(int type:{1,2,3}) for(bool provided:{false,true}) for(long step:{-2L,0L,3L}) {
        parse_ok=parse;have_row=exists;have_column=field;new_row=fresh;have_amount=provided;amount.integer=step;amount.floating=step+0.25;
        for(auto pair:{std::pair{original::incr,selected::incr},std::pair{original::decr,selected::decr}}) {
            auto a=run(pair.first,type),b=run(pair.second,type);
            assert(a.events==b.events && a.bytes==b.bytes && a.result.kind==b.result.kind && a.result.integer==b.result.integer && a.result.floating==b.result.floating);
            ++checks;
        }
    }
    size_t read_checks=0;
    for(auto name:{std::string(),std::string("name"),std::string("n\0x",3)}) {
        std::vector<TableColumn> columns(3);
        for(int i=0;i<3;++i) { columns[i].type=static_cast<TableColumn::Type>(i+1);columns[i].name=name+char('0'+i); }
        std::vector<TableColumn *> pointers{&columns[0],&columns[1],&columns[2]};table.column_list=&pointers;
        row.bytes.fill(0);long value=7;std::memcpy(row.data,&value,sizeof(value));
        zval original_array,selected_array;
        trace.clear();original::table_row2array(&table,&row,&original_array);auto original_trace=trace;
        trace.clear();selected::table_row2array(&table,&row,&selected_array);
        assert(trace==original_trace && original_array.array==selected_array.array);++read_checks;
        for(int type:{1,2,3}) for(bool present:{false,true}) {
            have_column=present;column.type=static_cast<TableColumn::Type>(type);zend_string field{name};
            zval original_value,selected_value;
            trace.clear();original::table_get_field_value(&table,&row,&original_value,&field);original_trace=trace;
            trace.clear();selected::table_get_field_value(&table,&row,&selected_value,&field);
            assert(trace==original_trace && original_value.kind==selected_value.kind && original_value.text==selected_value.text &&
                   original_value.integer==selected_value.integer && original_value.floating==selected_value.floating);
            ++read_checks;
        }
    }
    size_t cursor_errors=0;
    std::vector<TableColumn> failure_columns(3);
    for(int i=0;i<3;++i) { failure_columns[i].type=TableColumn::TYPE_INT;failure_columns[i].name="failure"+std::to_string(i); }
    std::vector<TableColumn *> failure_pointers{&failure_columns[0],&failure_columns[1],&failure_columns[2]};table.column_list=&failure_pointers;
    for(int fail_after:{0,1,3}) {
        cursor_failure_after=fail_after;zval partial;trace.clear();
        assert(!selected::table_row2array(&table,&row,&partial));
        assert(partial.kind==5 && partial.array.size()==size_t(fail_after));++cursor_errors;
    }
    cursor_failure_after=-1;
    std::printf("{\"actual_table_arithmetic_effect_traces\":%zu,\"actual_table_read_effect_traces\":%zu,\"selected_partial_array_cursor_errors\":%zu}\n",checks,read_checks,cursor_errors);
}
