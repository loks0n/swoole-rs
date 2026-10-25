"""No native execution: request, configured SDK, import and origin refusals."""
import unittest
import owned_sockets_identity as identity


class OwnedSocketsIdentity(unittest.TestCase):
    def test_independent_explicit_request_and_source(self):
        good = {identity.KEY: True, 'rust_sources_sha256': {identity.SOURCE: 'digest'}}
        self.assertTrue(identity.requested(good, True))
        for invalid in ({}, {identity.KEY: 1}, {identity.KEY: True},
                        {'reactor_defer_owned_requested': True, 'rust_sources_sha256': {identity.SOURCE: 'digest'}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                identity.requested(invalid, True)
        for inputs in ({}, {identity.KEY: False}):
            self.assertFalse(identity.requested(inputs, False))
        with self.assertRaises(ValueError):identity.requested(good, False)

    def test_configured_owner_is_independent_and_literal(self):
        self.assertTrue(identity.storage.configured('#define '+identity.MACRO+' 1', True, macro=identity.MACRO))
        for text in ('', '#define SWOOLE_RS_REACTOR_IOV_OWNED 1', '#define '+identity.MACRO+' OTHER',
                     '#define '+identity.MACRO+' 1\n#undef '+identity.MACRO):
            with self.subTest(text=text), self.assertRaises(ValueError):
                identity.storage.configured(text, True, macro=identity.MACRO)
        self.assertFalse(identity.storage.configured('', False, macro=identity.MACRO))

    def test_exact_imports_origins_and_qualified_policy(self):
        extension='/immutable/selected.so'
        result=dict(registry_owned_compiled=1,registry_policy=1,registry_len_image=extension,registry_policy_image=extension)
        symbols=identity.LENGTH+'\n'+identity.POLICY
        identity.consumer(result,symbols,extension,True)
        for key,value in [('registry_owned_compiled',0),('registry_policy',0),('registry_policy',2),
                          ('registry_len_image',None),('registry_policy_image','/other.so')]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                identity.consumer(dict(result,**{key:value}),symbols,extension,True)
        for symbol in (identity.LENGTH,identity.POLICY):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                identity.consumer(result,symbols.replace(symbol,symbol+'_unrelated'),extension,True)
        # Darwin nm's leading underscore is spelling, not another symbol.
        identity.consumer(result,'\n'.join(' U _'+s for s in (identity.LENGTH,identity.POLICY)),extension,True)

    def test_native_control_stays_off(self):
        result=dict(registry_owned_compiled=0,registry_policy=0,registry_len_image=None,registry_policy_image=None)
        identity.consumer(result,'','/immutable/native.so',False)
        for symbol in (identity.LENGTH,identity.POLICY):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                identity.consumer(result,symbol,'/immutable/native.so',False)
        with self.assertRaises(ValueError):
            identity.consumer(dict(result,registry_len_image='/immutable/native.so'),'','/immutable/native.so',False)



if __name__ == '__main__':unittest.main()
