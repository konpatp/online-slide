"""A migration branches state only after proving the current human baseline."""
# test-tier: every-time
import copy,unittest
from pathlib import Path
from slidekit import load_catalog,reconcile_state,empty_state,ContractError
from prepare_migration import prepare

class MigrationGenerationTests(unittest.TestCase):
    def setUp(self):
        self.catalog=load_catalog(Path(__file__).resolve().parents[1]/'slides')
        self.old=reconcile_state(empty_state(),self.catalog)[0]
        self.old['revision']=19
        self.new=copy.deepcopy(self.old)
    def test_preparation_leaves_original_state_unchanged(self):
        before=copy.deepcopy(self.old)
        proposed,receipt=prepare(self.old,self.old,self.new,self.catalog)
        self.assertEqual(self.old,before);self.assertEqual(proposed['revision'],20)
        self.assertTrue(receipt['oldStateUntouched'])
    def test_new_human_edit_and_order_visibility_loss_fail_closed(self):
        changed=copy.deepcopy(self.old);changed['revision']+=1
        with self.assertRaisesRegex(ContractError,'baseline'):prepare(self.old,changed,self.new,self.catalog)
        self.new['order'].reverse()
        with self.assertRaisesRegex(ContractError,'order'):prepare(self.old,self.old,self.new,self.catalog)
        self.new=copy.deepcopy(self.old);self.new['hidden']=[self.new['order'][0]]
        with self.assertRaisesRegex(ContractError,'visibility'):prepare(self.old,self.old,self.new,self.catalog)
    def test_saved_text_cannot_be_replaced_by_a_migration(self):
        sid=self.old['order'][0];key=self.catalog[sid]['headline']
        self.old['overlays']={sid:{key:{'text':'Human headline'}}}
        with self.assertRaisesRegex(ContractError,'retained human overlays'):prepare(self.old,self.old,self.new,self.catalog)
if __name__=='__main__':unittest.main()
