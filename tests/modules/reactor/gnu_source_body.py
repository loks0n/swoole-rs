"""Render an inert GNU source-body oracle; never an installed Linux oracle.

The facade supplies typed metadata nodes/allocation helpers. It does not model
Native allocation, exception, destruction or resource behavior.
"""
import hashlib
from pathlib import Path
import re

INPUTS = {
    'candidate-headers/usr/include/aarch64-linux-gnu/c++/12/bits/c++config.h': '1b9e6dc3c4c345d213148e0760a0d120d85a370edbabf7b4c2dbbcd95be05c8b',
    'candidate-headers/usr/include/c++/12/bits/functional_hash.h': '7dc5a4e3677ab369da48909df74eaea00f516f3107303855258ac8c7560d79f6',
    'candidate-headers/usr/include/c++/12/bits/hash_bytes.h': '72a33aca3921a4fa2cbe77f5647998c6dba0ae0e2f868b4cb066f06877b43b1c',
    'candidate-headers/usr/include/c++/12/bits/hashtable_policy.h': '59d76541faeda87c8936f4b0455ed09d14cae3b39fda2141815e4f4091b86ac0',
    'candidate-headers/usr/include/c++/12/bits/unordered_map.h': 'af70ad617fe4ec6a6fd8f7166170f889880558534edef5e0a4ac4c8057724a5e',
    'candidate-headers/usr/include/c++/12/unordered_map': '6b1a97c6e0df6719542e2278e5cdcb32864a79dc98d3df85e114fdbe39c59c88',
    'candidate-headers/usr/include/c++/12/bits/hashtable.h': 'd1cad098a5169c9bcb04ce63a58697b91f3f441b5f360e64a01e23ba3bed8a9c',
    'mirror-hashtable_c++0x.cc': 'e63690b5ef14c78d0414148e6cc1f6da982de3afed2d0adac7faecbaa649c7fb',
    'mirror-hashtable-aux.cc': '68fe03dda8fe9d33ec38b535cd9a750119da0da461b6040117fc114674ce893e',
}


def definition(text, pattern):
    """Require one definition; a declaration may never select a later brace."""
    matches = list(re.finditer(pattern+r'\s*\{', text))
    if len(matches) != 1:
        raise ValueError('Expected exactly one source definition: '+pattern)
    opening = matches[0].end()-1
    depth, end = 1, opening+1
    while depth:
        if end == len(text):raise ValueError('Unterminated source body')
        depth += (text[end] == '{')-(text[end] == '}')
        end += 1
    return text[opening:end]


def render(candidate):
    candidate = Path(candidate)
    inputs = {}
    for relative, expected in INPUTS.items():
        data = (candidate/relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Official candidate input changed: '+relative)
        inputs[relative] = data.decode()
    header = inputs['candidate-headers/usr/include/c++/12/bits/hashtable.h']
    policy = inputs['mirror-hashtable_c++0x.cc']
    bodies = {
        'next_bucket': definition(policy, r'_Prime_rehash_policy::_M_next_bkt\(std::size_t __n\) const'),
        'need_rehash': definition(policy, r'_M_need_rehash\(std::size_t __n_bkt, std::size_t __n_elt,\s*std::size_t __n_ins\) const'),
        'insert_bucket': definition(header, r'_M_insert_bucket_begin\(size_type __bkt, __node_ptr __node\)'),
        'unique_rehash': definition(header, r'_M_rehash_aux\(size_type __bkt_count, true_type /\* __uks \*/\)'),
        'remove_bucket': definition(header, r'_M_remove_bucket_begin\(size_type __bkt, __node_ptr __next,\s*size_type __next_bkt\)'),
        'erase': definition(header, r'_M_erase\(size_type __bkt, __node_base_ptr __prev_n, __node_ptr __n\)\s*-> iterator'),
        'assign': definition(header, r'_M_assign\(_Ht&& __ht, const _NodeGenerator& __node_gen\)'),
        'clear': definition(header, r'clear\(\) noexcept'),
    }
    table = inputs['mirror-hashtable-aux.cc'].split('extern const unsigned long __prime_list[]',1)[1].split('{',1)[1].split('};',1)[0]
    common, conditional = table.split('#if __SIZEOF_LONG__ != 8',1)
    wide = conditional.split('#else',1)[1].split('#endif',1)[0]
    primes = [int(value) for value in re.findall(r'(\d+)ul',common+wide)]
    if len(primes)!=305 or primes[-1]!=primes[-2]:raise ValueError('Unexpected unsigned-long64 prime metadata')
    primes.pop()  # duplicated ABI sentinel, never a distinct policy value
    prelude = r'''
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <type_traits>
#include <utility>
#include <vector>
#ifndef __try
#define __try try
#define __catch(x) catch(x)
#define __throw_exception_again throw
#endif
static_assert(sizeof(unsigned long)==8 && sizeof(size_t)==8,"Candidate unsigned-long64 metadata only");
'''
    prelude += inputs['mirror-hashtable-aux.cc']
    prelude += r'''
using __detail::__prime_list;
template<class Ht,class Value> const Value &__fwd_value_for(const Value &value) { return value; }
class GnuSourcePrime {
    float _M_max_load_factor=1;
    mutable size_t _M_next_resize=0;
    static constexpr size_t _S_growth_factor=2;
public:
    size_t next_resize() const { return _M_next_resize; }
    size_t _M_next_bkt(size_t __n) const @next_bucket@
    std::pair<bool,size_t> _M_need_rehash(size_t __n_bkt,size_t __n_elt,size_t __n_ins) const @need_rehash@
};
template<class Key> class GnuSource {
    using Entry=std::pair<const Key,uintptr_t>;
    struct NodeBase { NodeBase *_M_nxt=nullptr; };
    struct Node:NodeBase {
        Entry value;bool live=true;
        Node(Key key,uintptr_t token):value(key,token) {}
        Node *_M_next() const { return static_cast<Node*>(this->_M_nxt); }
        const Entry &_M_v() const { return value; }
    };
    using size_type=size_t;
    using __node_ptr=Node*;
    using __node_base_ptr=NodeBase*;
    using __buckets_ptr=NodeBase**;
    using iterator=Node*;
    struct __hash_code_base {
        static size_t _M_bucket_index(const Node &node,size_t count) { return static_cast<size_t>(node.value.first)%count; }
    };
    NodeBase _M_before_begin;
    size_t _M_bucket_count=1,_M_element_count=0;
    __buckets_ptr _M_buckets=nullptr;
    GnuSourcePrime prime;
    std::vector<std::unique_ptr<Node>> nodes;
    std::vector<std::unique_ptr<NodeBase*[]>> bucket_storage;
    // Inert allocation helpers retain metadata until the test facade ends.
    // Actual GNU allocator/deallocation/exception traces are NOT modeled.
    __buckets_ptr _M_allocate_buckets(size_t n) {
        bucket_storage.emplace_back(new NodeBase*[n]());return bucket_storage.back().get();
    }
    void _M_deallocate_buckets() {}
    void _M_deallocate_node(Node *node) { node->live=false; }
    void _M_deallocate_nodes(Node *node) { while(node){node->live=false;node=node->_M_next();} }
    void _M_copy_code(Node &,const Node &) {}
    size_t _M_bucket_index(const Node &node) const { return __hash_code_base::_M_bucket_index(node,_M_bucket_count); }
    Node *_M_begin() const { return static_cast<Node*>(_M_before_begin._M_nxt); }
    void _M_update_bbegin(Node *node) { _M_before_begin._M_nxt=node;_M_buckets[_M_bucket_index(*node)]=&_M_before_begin; }
    Node *allocate(Key key,uintptr_t token) { nodes.emplace_back(new Node(key,token));return nodes.back().get(); }
    void _M_insert_bucket_begin(size_type __bkt,__node_ptr __node) @insert_bucket@
    void _M_rehash_aux(size_type __bkt_count,std::true_type) @unique_rehash@
    void _M_remove_bucket_begin(size_type __bkt,__node_ptr __next,size_type __next_bkt) @remove_bucket@
    iterator _M_erase(size_type __bkt,__node_base_ptr __prev_n,__node_ptr __n) @erase@
    template<class _Ht,class _NodeGenerator> void _M_assign(_Ht&& __ht,const _NodeGenerator& __node_gen) @assign@
public:
    GnuSource() { _M_buckets=_M_allocate_buckets(1); }
    GnuSource(const GnuSource &other):_M_bucket_count(other._M_bucket_count),_M_element_count(other._M_element_count),prime(other.prime) {
        auto generator=[this](const Entry &value){return allocate(value.first,value.second);};
        _M_assign(other,generator);
    }
    size_t size() const { return _M_element_count; }
    size_t buckets() const { return _M_bucket_count; }
    size_t threshold() const { return prime.next_resize(); }
    void put(Key key,uintptr_t token) {
        for(Node *n=_M_begin();n;n=n->_M_next())if(n->value.first==key){n->value.second=token;return;}
        auto growth=prime._M_need_rehash(_M_bucket_count,_M_element_count,1);
        if(growth.first)_M_rehash_aux(growth.second,std::true_type{});
        Node *node=allocate(key,token);_M_insert_bucket_begin(_M_bucket_index(*node),node);++_M_element_count;
    }
    uintptr_t get(Key key) {
        for(Node *n=_M_begin();n;n=n->_M_next())if(n->value.first==key)return n->value.second;
        put(key,0);return 0;
    }
    void erase(Key key) {
        NodeBase *previous=&_M_before_begin;
        for(Node *n=_M_begin();n;previous=n,n=n->_M_next())if(n->value.first==key){_M_erase(_M_bucket_index(*n),previous,n);return;}
    }
    void clear() noexcept @clear@
    std::vector<std::pair<Key,uintptr_t>> values() const {
        std::vector<std::pair<Key,uintptr_t>> result;
        for(Node *n=_M_begin();n;n=n->_M_next())result.emplace_back(n->value.first,n->value.second);
        return result;
    }
};
'''
    for key, body in bodies.items():prelude = prelude.replace('@'+key+'@', body)
    if re.search(r'@\w+@',prelude):raise ValueError('Unexpanded body marker')
    return prelude, dict(input_sha256=INPUTS,prime_values_u64=primes,source_bodies=bodies,native_linux_qualified=False,allocator_effects_modeled=False)
