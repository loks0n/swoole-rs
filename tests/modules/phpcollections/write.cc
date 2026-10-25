// Complete original/selected Table::set bodies over scripted native effects.
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include <vector>
#include "swoole_rs_phpcollections.h"
struct HashTable;
struct zval { int kind=0; long integer=0; double floating=0; std::string text; HashTable *array=nullptr; };
struct Entry { std::string key; bool numeric=false; zval value; };
struct HashTable { std::vector<Entry> entries; };
struct zend_string { std::string value; };
static std::vector<std::string> trace;
static bool parse_ok, ready, have_row, fresh, mutate;
static bool descriptor_lookup_failure=false, descriptor_name_failure=false, descriptor_store_failure=false;
static HashTable input;
static zval array_value;
struct TableRow;
struct TableColumn {
    enum Type { TYPE_INT=1, TYPE_FLOAT=2, TYPE_STRING=3 };
    int type=1; size_t index=0; std::string name;
    void clear(TableRow *) const;
};
static std::vector<TableColumn> columns;
struct TableRow {
    std::vector<std::string> values;
    void unlock() { trace.push_back("unlock"); }
    void set_value(const TableColumn *col,const char *value,size_t length) {
        trace.push_back("write-string:"+col->name);values[col->index]=std::string("string:")+std::string(value,length);
    }
    void set_value(const TableColumn *col,double *value,size_t) {
        trace.push_back("write-double:"+col->name);values[col->index]="double:"+std::to_string(*value);
    }
    void set_value(const TableColumn *col,long *value,size_t) {
        trace.push_back("write-long:"+col->name);values[col->index]="long:"+std::to_string(*value);
    }
};
void TableColumn::clear(TableRow *row) const { trace.push_back("clear:"+name);row->values[index]="clear"; }
static TableRow row,lock_row;
#define SW_TABLE_FLAG_NEW_ROW 1
#define SW_TABLE_KEY_SIZE 64
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
    bool ready() { trace.push_back("ready");return ::ready; }
    TableRow *set(const char *key,size_t length,TableRow **lock,int *flags) {
        trace.push_back("set:"+std::string(key,length));*lock=&lock_row;*flags=fresh?1:0;return have_row?&row:nullptr;
    }
    TableColumn *get_column(std::string name) {
        trace.push_back("column:"+name);
        for(auto &col : ::columns) if(col.name==name)return &col;
        return nullptr;
    }
};
// Scripted descriptor adapter over the SAME fixture vector, not real Rust storage.
struct TableV2 : Table {
    struct Column {
        TableColumn *value=nullptr;
        mutable bool error=false;
        int copied_kind=0;
        size_t copied_index=0;
        Column(TableColumn *source=nullptr,bool failed=false):value(source),error(failed),copied_kind(source?source->type:0),copied_index(source?source->index:0) {}
        bool valid() const { return value!=nullptr && !error; }
        bool failed() const { return error; }
        int kind() const { return copied_kind; }
        size_t index() const { return copied_index; }
        size_t name_length() const { return value->name.size(); }
        bool copy_name(char *output,size_t capacity) const {
            if(descriptor_name_failure) { error=true;return false; }
            if(!value || capacity<name_length())return false;
            if(name_length())std::memcpy(output,value->name.data(),name_length());
            return true;
        }
        bool clear_value(TableRow *row) const { value->clear(row);return true; }
        bool set_value(TableRow *row,const void *input,size_t length) const {
            if(descriptor_store_failure) { trace.push_back("store-failed");return false; }
            if(kind()==TableColumn::TYPE_STRING)row->set_value(value,static_cast<const char *>(input),length);
            else if(kind()==TableColumn::TYPE_FLOAT)row->set_value(value,const_cast<double *>(static_cast<const double *>(input)),length);
            else row->set_value(value,const_cast<long *>(static_cast<const long *>(input)),length);
            return true;
        }
    };
    struct Cursor {
        Table::Cursor source;
        bool next(Column &out) { out=Column{const_cast<TableColumn *>(source.next())};return out.valid(); }
        bool failed() const { return source.failed(); }
    };
    Cursor columns() const { return {Table::columns()}; }
    Column get_column(std::string name) { return {Table::get_column(std::move(name)),descriptor_lookup_failure}; }
};
struct Execute {};
static TableV2 table;
static TableV2 *table_get_and_check_ptr2(Execute *) { trace.push_back("table");return &table; }
static zval *zend_hash_str_find(HashTable *ht,const char *key,size_t length) {
    trace.push_back("lookup:"+std::string(key,length));
    for(auto &entry:ht->entries)if(!entry.numeric && entry.key==std::string(key,length))return &entry.value;
    return nullptr;
}
static void conversion_effect() { if(mutate)columns[2].type=2; }
static zend_string *zval_get_string(zval *value) {
    trace.push_back("convert-string");conversion_effect();return new zend_string{value->kind?value->text:std::string()};
}
static double zval_get_double(zval *value) { trace.push_back("convert-double");conversion_effect();return value->kind?value->floating:0; }
static long zval_get_long(zval *value) { trace.push_back("convert-long");conversion_effect();return value->kind?value->integer:0; }
static void zend_string_release(zend_string *value) { trace.push_back("release-string");delete value; }
static void warning(int,const char *format,...) {
    char output[512];va_list args;va_start(args,format);std::vsnprintf(output,sizeof(output),format,args);va_end(args);
    trace.push_back("warning:"+std::string(output));
}
static void zend_throw_error(void *,const char *) { trace.push_back("cursor-error"); }
static std::string key_value;
#define PHP_METHOD(cls,name) void name(Execute *execute_data,zval *return_value)
#define ZEND_THIS execute_data
#define ZEND_PARSE_PARAMS_THROW 0
#define ZEND_PARSE_PARAMETERS_START_EX(flags,min,max) trace.push_back("parse");if(!parse_ok){RETURN_FALSE;}
#define Z_PARAM_STRING(key,length) key=key_value.data();length=key_value.size();
#define Z_PARAM_ARRAY(value) value=&array_value;
#define ZEND_PARSE_PARAMETERS_END_EX(failure)
#define Z_ARRVAL_P(value) ((value)->array)
#define ZVAL_IS_NULL(value) ((value)->kind==0)
#define ZSTR_VAL(p) ((p)->value.data())
#define ZSTR_LEN(p) ((p)->value.size())
#define php_swoole_fatal_error(...) warning(__VA_ARGS__)
#define php_swoole_error(...) warning(__VA_ARGS__)
#define E_ERROR 1
#define E_WARNING 2
#define RETURN_FALSE do { trace.push_back("false");return_value->integer=0;return; } while(0)
#define RETURN_TRUE do { trace.push_back("true");return_value->integer=1;return; } while(0)
#define SW_HASHTABLE_FOREACH_START2(ht,k,klen,ktype,zv) for(auto &entry:(ht)->entries){ k=entry.numeric?nullptr:entry.key.data();klen=entry.key.size();ktype=entry.numeric?1:0;zv=&entry.value;
#define SW_HASHTABLE_FOREACH_END() }
namespace original {
#include "native-write.inc"
}
namespace selected {
#include "selected-write.inc"
}
struct Observation { std::vector<std::string> events,values;long result; };
static Observation run(void(*method)(Execute *,zval *),int layout) {
    columns={{3,0,std::string("s\0x",3)},{2,1,"f"},{layout,2,"i"}};
    std::vector<TableColumn *> pointers;for(auto &col:columns)pointers.push_back(&col);
    table.column_list=&pointers;row.values={"before-s","before-f","before-i"};trace.clear();
    Execute execute;zval result;result.integer=-1;method(&execute,&result);return {trace,row.values,result.integer};
}
int main() {
    size_t checks=0;
    for(bool parse:{false,true})for(bool rdy:{false,true})for(bool exists:{false,true})
    for(bool new_row:{false,true})for(bool effect:{false,true})for(int layout:{1,2,3,77})
    for(int shape=0;shape<6;++shape)for(bool null:{false,true})for(size_t length:{size_t(0),size_t(5),size_t(64)}) {
        parse_ok=parse;ready=rdy;have_row=exists;fresh=new_row;mutate=effect;key_value=std::string(length,'k');
        if(length==5)key_value[1]='\0';
        input.entries.clear();
        for(int i=0;i<3;++i) {
            if(shape==1 && i==1)continue;
            zval value;value.kind=null?0:1;value.integer=-7+i;value.floating=2.5+i;value.text=std::string("v\0",2)+char('a'+i);
            std::string name=i==0?std::string("s\0x",3):(i==1?"f":"i");
            input.entries.push_back({name,shape==2 && i==1,value});
        }
        if(shape==3)input.entries.push_back({"unknown",false,{}});
        if(shape==4)input.entries.clear();
        if(shape==5)std::swap(input.entries[0],input.entries[2]);
        array_value.array=&input;
        auto a=run(original::set,layout),b=run(selected::set,layout);
        assert(a.events==b.events && a.values==b.values && a.result==b.result);++checks;
    }
    size_t error_checks=0;
    parse_ok=ready=have_row=fresh=true;mutate=false;key_value="row";input.entries.clear();array_value.array=&input;
    for(int fail_after:{0,1,3}) {
        cursor_failure_after=fail_after;auto observed=run(selected::set,1);
        assert(observed.result==0 && observed.events.size()>=3);
        const auto end=observed.events.end();
        assert(*(end-3)=="unlock" && *(end-2)=="cursor-error" && *(end-1)=="false");
        for(int i=0;i<fail_after;++i) assert(observed.values[i]=="clear");
        ++error_checks;
    }
    cursor_failure_after=-1;
    // Scripted failure statuses over live records; no original invalidation/reentry.
    size_t descriptor_errors=0;
    fresh=false;input.entries={{std::string("s\0x",3),false,{1,0,0,"live-string",nullptr}}};
    descriptor_lookup_failure=true;
    auto lookup=run(selected::set,1);
    assert(lookup.result==0 && lookup.events[lookup.events.size()-3]=="unlock" && lookup.events.back()=="false");
    descriptor_lookup_failure=false;++descriptor_errors;
    descriptor_store_failure=true;
    auto store=run(selected::set,1);
    const std::vector<std::string> tail={"store-failed","release-string","unlock","cursor-error","false"};
    assert(store.events.size()>=tail.size() && std::vector<std::string>(store.events.end()-tail.size(),store.events.end())==tail);
    assert(store.values[0]=="before-s");
    descriptor_store_failure=false;++descriptor_errors;
    fresh=true;descriptor_name_failure=true;
    auto name=run(selected::set,1);
    assert(name.result==0 && name.events[name.events.size()-3]=="unlock" && name.events.back()=="false");
    assert(name.values==std::vector<std::string>({"before-s","before-f","before-i"}));
    descriptor_name_failure=false;++descriptor_errors;
    std::printf("{\"actual_table_set_effect_traces\":%zu,\"selected_cursor_error_prefixes\":%zu,\"selected_descriptor_error_prefixes\":%zu}\n",checks,error_checks,descriptor_errors);
}
