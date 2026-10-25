#include <php.h>
#include <Zend/zend_exceptions.h>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>
#include "swoole.h"
#include "swoole_log.h"
#include "macro-profile.h"
static std::vector<std::string> events;
static unsigned error_reads, formats, enum_reads;
static int code() { events.push_back("error" + std::to_string(++error_reads)); return 777789; }
static const char *payload() { ++formats; return "operand"; }
static void check(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }
struct Proxy {
    bool accept;
    explicit operator bool() const { events.push_back("bool"); return accept; }
    ~Proxy() { events.push_back("proxy-dtor"); }
};
struct Level {
    bool accept;
    explicit Level(bool v) : accept(v) { events.push_back("ctor"); }
    Level(const Level &) = delete;
    Level(Level &&) = delete;
    ~Level() { events.push_back("level-dtor"); }
    operator int() const { events.push_back("convert"); return SW_LOG_WARNING; }
};
static Proxy operator>=(const Level &value, int threshold) {
    check(threshold == SW_LOG_INFO, "fresh threshold");
    events.push_back("compare"); return {value.accept};
}
struct AndProxy {
    bool accept;
    Proxy operator&&(bool right) const { events.push_back("and"); return {accept && right}; }
    ~AndProxy() { events.push_back("and-dtor"); }
};
struct AndLevel : Level { using Level::Level; };
static AndProxy operator>=(const AndLevel &value, int threshold) {
    check(threshold == SW_LOG_INFO, "and threshold");
    events.push_back("compare"); return {value.accept};
}
struct ThrowLevel : Level { using Level::Level; };
static bool operator>=(const ThrowLevel &, int threshold) {
    check(threshold == SW_LOG_INFO, "throw threshold");
    events.push_back("throw"); throw std::runtime_error("external operator");
}
struct NumericTemporary {
    NumericTemporary() { events.push_back("numeric-ctor"); }
    ~NumericTemporary() { events.push_back("numeric-dtor"); }
};
namespace operand_enum {
enum Level { warning = SW_LOG_WARNING };
static bool operator>=(Level, int) { ++enum_reads; return false; }
}
ZEND_BEGIN_ARG_INFO_EX(arginfo_operand, 0, 0, 1)
 ZEND_ARG_TYPE_INFO(0, directory, IS_STRING, 0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(m14_macro_profile) {
 char *directory; size_t length;
 ZEND_PARSE_PARAMETERS_START(1, 1) Z_PARAM_STRING(directory, length) ZEND_PARSE_PARAMETERS_END();
 try {
    auto *logger = sw_logger(); logger->close(); logger->reset();
    check(logger->set_date_format("OPERAND"), "date");
    const auto path = std::string(directory, length) + "/macro.log";
    check(logger->open(path.c_str()), "open");
    logger->set_level(SW_LOG_DEBUG);
    float fractional_float = -0.25f;
    double fractional_double = -0.25;
    long double fractional_long = -0.25L;
    swoole_error_log(fractional_float, 777789, "%s", payload());
    swoole_error_log(fractional_double, 777789, "%s", payload());
    swoole_error_log(fractional_long, 777789, "%s", payload());
    check(formats == 0, "negative fractions must filter before conversion to int");
    logger->set_level(SW_LOG_INFO);
    swoole_error_log(std::nextafter(2.0L, 0.0L), 777789, "%s", payload());
    check(formats == 0, "long double below threshold");
    swoole_error_log(std::nextafter(2.0L, 3.0L), 777789, "%s", payload());
    check(formats == 1, "long double above threshold");
#ifdef __SIZEOF_INT128__
    __int128 wide_negative = -(__int128(1) << 100);
    unsigned __int128 wide_positive = (static_cast<unsigned __int128>(1) << 100) | 2;
    swoole_error_log(wide_negative, 777789, "%s", payload());
    check(formats == 1, "negative extended integer");
    swoole_error_log(wide_positive, 777789, "%s", payload());
    check(formats == 2, "extended high bits preserved");
#endif
    swoole_error_log(operand_enum::warning, 777789, "%s", payload());
    check(enum_reads == 1, "enum operator must execute");
    std::vector<std::vector<std::string>> traces;
    events.clear(); error_reads = 0;
    swoole_error_log(Level(true), code(), "operator");
    check(error_reads == 3, "accepted external error reads"); traces.push_back(events);
    check(events == std::vector<std::string>({"error1","ctor","compare","bool","error2","proxy-dtor","level-dtor","error3","ctor","convert","level-dtor"}), "external temporary spans ignored query");
    events.clear(); error_reads = 0;
    swoole_error_log(Level(false), code(), "operator");
    check(error_reads == 1, "false external comparison short circuits"); traces.push_back(events);
    events.clear(); error_reads = 0;
    swoole_error_log(AndLevel(false), code(), "operator");
    check(error_reads == 2, "overloaded and evaluates right operand"); traces.push_back(events);
    events.clear(); error_reads = 0;
    swoole_error_log((NumericTemporary(), SW_LOG_WARNING), code(), "numeric");
    check(events == std::vector<std::string>({"error1","numeric-ctor","error2","numeric-dtor","error3","numeric-ctor","numeric-dtor"}), "numeric expression temporary spans ignored query"); traces.push_back(events);
    events.clear(); error_reads = 0;
    try { swoole_error_log(ThrowLevel(true), code(), "operator"); check(false, "operator must throw"); }
    catch (const std::runtime_error &e) { check(std::string(e.what()) == "external operator", "exact external exception"); events.push_back("caught"); }
    check(events == std::vector<std::string>({"error1","ctor","throw","level-dtor","caught"}), "native exception prefix"); traces.push_back(events);
    logger->close();
    array_init(return_value); add_assoc_long(return_value,"formats",formats); add_assoc_long(return_value,"enum_reads",enum_reads);
    zval result; array_init(&result);
    for (const auto &trace : traces) { zval row; array_init(&row); for (const auto &value : trace) add_next_index_stringl(&row,value.data(),value.size()); add_next_index_zval(&result,&row); }
    add_assoc_zval(return_value,"traces",&result);
 } catch (const std::exception &e) { zend_throw_exception(zend_ce_exception,e.what(),0); }
}
static const zend_function_entry functions[] = { PHP_FE(m14_macro_profile,arginfo_operand) PHP_FE_END };
extern "C" {
zend_module_entry m14_macro_profile_module_entry = { STANDARD_MODULE_HEADER,"m14_macro_profile",functions,nullptr,nullptr,nullptr,nullptr,nullptr,"0",STANDARD_MODULE_PROPERTIES };
ZEND_GET_MODULE(m14_macro_profile)
}
