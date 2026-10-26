"""Identity fixtures only: no DSO loading, allocation or native execution."""
import unittest
import owned_iov_identity as identity


class OwnedIovIdentity(unittest.TestCase):
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


if __name__ == '__main__':unittest.main()
