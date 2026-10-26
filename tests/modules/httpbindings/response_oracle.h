#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <clocale>
#include <climits>
#include <cstdio>
#include <cstring>
#include <strings.h>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#define ZEND_STRL(s) s,sizeof(s)-1
#define SW_STRL(s) s,sizeof(s)-1
#define SW_STRCASEEQ(s,n,v) swoole_strcaseeq(s,n,SW_STRL(v))
#define RESPONSE_DECL(N) namespace N {int header(const std::string&);}
RESPONSE_DECL(upstream_response)
RESPONSE_DECL(candidate_response)
