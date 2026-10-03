import unittest
from main import build_document
from starintel_canonical import validate_document

class ContractTests(unittest.TestCase):
    def test_generators_emit_flat_canonical_documents(self):
        for dtype, raw in [('person', {'fname':'Ada','race':'generated','dob':''}), ('message', {'content':'Hi','platform':'synthetic','isReply':False,'user':'ada','mentions':['bob']}), ('socialmediapost', {'content':'Post','url':'','media':['https://example.invalid/photo']})]:
            with self.subTest(dtype=dtype):
                doc=build_document(dtype,raw,'test')
                validate_document(doc)
                self.assertEqual(doc['schemaVersion'],'0.10.1')
                self.assertNotIn('data',doc)
                self.assertNotIn('_id',doc)
                self.assertTrue(doc['extensions']['star_synthdata']['synthetic'])
        self.assertFalse(build_document('message',{'content':'x','platform':'x','isReply':False},'t')['isReply'])

    def test_invalid_generated_field_rejected(self):
        with self.assertRaises(ValueError):
            build_document('person',{'dob':'not-a-date'},'t')

    def test_handles_are_not_fabricated_references(self):
        doc=build_document('message',{'content':'x','platform':'x','user':'alice'},'t')
        self.assertNotIn('user',doc)
        self.assertEqual(doc['extensions']['star_synthdata']['generatedMetadata']['user'],'alice')

if __name__=='__main__': unittest.main()
