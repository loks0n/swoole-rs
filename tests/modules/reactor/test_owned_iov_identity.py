"""Identity fixtures only: no DSO loading, allocation or native execution."""
import unittest
import owned_iov_identity as identity


class OwnedIovIdentity(unittest.TestCase):
    def test_request_requires_explicit_boolean_and_source(self):
        self.assertTrue(identity.requested({identity.KEY: True, 'rust_sources_sha256': {identity.SOURCE: 'digest'}}, True))
        for inputs in ({}, {identity.KEY: 1}, {identity.KEY: 'true'}, {identity.KEY: True}):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                identity.requested(inputs, True)

    def test_native_missing_or_false_is_off(self):
        self.assertFalse(identity.requested({}, False))
        self.assertFalse(identity.requested({identity.KEY: False}, False))
        with self.assertRaises(ValueError):identity.requested({identity.KEY: True}, False)

    def test_actual_config_requires_literal_selected_one(self):
        self.assertTrue(identity.configured('#define '+identity.MACRO+' 1\n', True))
        for text in ('', '#define '+identity.MACRO+' 0', '#define '+identity.MACRO+' OTHER', '#define '+identity.MACRO+' 1\n#undef '+identity.MACRO, '#define '+identity.MACRO+' 1\n#define '+identity.MACRO+' 1'):
            with self.subTest(text=text), self.assertRaises(ValueError):identity.configured(text, True)

    def test_native_config_stays_off(self):
        for text in ('/* #undef '+identity.MACRO+' */', '#define '+identity.MACRO+' 0'):
            self.assertFalse(identity.configured(text, False))
        with self.assertRaises(ValueError):identity.configured('#define '+identity.MACRO+' 1', False)

    def test_actual_imports_and_origins_are_required(self):
        extension='/immutable/selected.so'
        result=dict(iov_constructor_image=extension,iov_destructor_image=extension,iov_owned_compiled=1,iov_owned_length_image=extension)
        symbols='\n'.join((identity.CONSTRUCTOR,identity.DESTRUCTOR,identity.LENGTH))
        identity.consumer(result,symbols,extension,True)
        for key,value in [('iov_constructor_image','/other.so'),('iov_destructor_image',None),('iov_owned_length_image',None),('iov_owned_compiled',0)]:
            with self.subTest(key=key), self.assertRaises(ValueError):identity.consumer(dict(result,**{key:value}),symbols,extension,True)
        with self.assertRaises(ValueError):identity.consumer(result,symbols.replace(identity.LENGTH,identity.LENGTH+'_unrelated'),extension,True)
        for symbol in (identity.CONSTRUCTOR,identity.DESTRUCTOR,identity.LENGTH):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):identity.consumer(result,symbols.replace(symbol,''),extension,True)

    def test_native_imports_remain_native(self):
        extension='/immutable/native.so'
        result=dict(iov_constructor_image=extension,iov_destructor_image=extension,iov_owned_compiled=0)
        symbols=identity.CONSTRUCTOR+'\n'+identity.DESTRUCTOR
        identity.consumer(result,symbols,extension,False)
        with self.assertRaises(ValueError):identity.consumer(result,symbols+'\n'+identity.LENGTH,extension,False)


class OwnedDeferIdentity(unittest.TestCase):
    key = 'reactor_defer_owned_requested'
    source = 'crates/reactor/src/deferred.rs'
    macro = 'SWOOLE_RS_REACTOR_DEFER_OWNED'

    def test_independent_request_and_source_are_required(self):
        inputs = {self.key: True, 'rust_sources_sha256': {self.source: 'digest'}}
        self.assertTrue(identity.requested(inputs, True, key=self.key, source=self.source))
        for invalid in ({identity.KEY: True, 'rust_sources_sha256': {identity.SOURCE: 'digest'}},
                        {self.key: True, 'rust_sources_sha256': {identity.SOURCE: 'digest'}},
                        {self.key: 1, 'rust_sources_sha256': {self.source: 'digest'}}):
            with self.subTest(inputs=invalid), self.assertRaises(ValueError):
                identity.requested(invalid, True, key=self.key, source=self.source)

    def test_native_request_remains_off(self):
        for inputs in ({}, {self.key: False}):
            self.assertFalse(identity.requested(inputs, False, key=self.key, source=self.source))
        with self.assertRaises(ValueError):
            identity.requested({self.key: True}, False, key=self.key, source=self.source)

    def test_config_is_independent_and_literal(self):
        self.assertTrue(identity.configured('#define '+self.macro+' 1', True, macro=self.macro))
        for text in ('#define '+identity.MACRO+' 1', '#define '+self.macro+' OTHER',
                     '#define '+self.macro+' 1\n#undef '+self.macro):
            with self.subTest(text=text), self.assertRaises(ValueError):
                identity.configured(text, True, macro=self.macro)
        self.assertFalse(identity.configured('', False, macro=self.macro))
        with self.assertRaises(ValueError):
            identity.configured('#define '+self.macro+' 1', False, macro=self.macro)


if __name__ == '__main__':unittest.main()
