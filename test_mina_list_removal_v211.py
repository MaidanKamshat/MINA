"""Offline exact-match and safety regression checks for MINA v2.11."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mina_list_removal_v211 import (
    ListRemovalError, is_list_removal_request, prepare_remove_item_action,
    preview_remove_item_action, commit_remove_item_action,
)


class RemovalParserTests(unittest.TestCase):
    def setUp(self):
        self.hub = {'stores': {
            'target': [{'id':'target1', 'name':'dish soap', 'done':False},
                       {'id':'target2', 'name':'toothpaste','done':False},
                       {'id':'target3','name':'mac and cheese','done':True}],
            'trader_joes': [{'id':'tj1','name':'toothpaste','done':False}],
            'costco':[{'id':'c1','name':'milk','done':False}]},
            'places': {'unrelated':'preserve'}, 'preferences': {'unrelated':'keep'}}
        self.command = 'Mina, remove toothpaste from my Target shopping list.'

    def test_exact_user_voice_phrase(self):
        self.assertTrue(is_list_removal_request(self.command))
        self.assertEqual(prepare_remove_item_action(self.command,self.hub),{
            'kind':'remove_item','store':'target','item_id':'target2','expected_name':'toothpaste'})

    def test_preview_not_saved(self):
        action=prepare_remove_item_action(self.command,self.hub)
        text=preview_remove_item_action(action)
        self.assertIn('not saved yet',text)
        self.assertIn('Target',text)
        self.assertIn('toothpaste',text)
        self.assertIn('Confirm item removal',text)
        self.assertEqual(len(self.hub['stores']['target']),3)

    def test_commit_exact_item_only(self):
        old=deepcopy(self.hub)
        action=prepare_remove_item_action(self.command,self.hub)
        new=commit_remove_item_action(self.hub,action)
        self.assertEqual([x['name'] for x in new['stores']['target']],['dish soap','mac and cheese'])
        self.assertEqual(new['stores']['trader_joes'],old['stores']['trader_joes'])
        self.assertEqual(new['stores']['costco'],old['stores']['costco'])
        self.assertEqual(new['places'],old['places'])
        self.assertEqual(self.hub,old)

    def test_no_confirmation_means_no_write(self):
        before=deepcopy(self.hub)
        prepare_remove_item_action(self.command,self.hub)
        self.assertEqual(self.hub,before)

    def test_punctuation_variants_and_no_wake_word(self):
        for q in ('remove toothpaste from Target list',
                  'Mina remove toothpaste from my Target shopping list',
                  'Hey Mina, please remove toothpaste from my Target grocery list!',
                  'MINA, DELETE TOOTHPASTE FROM OUR TARGET SHOPPING LIST.',
                  'take toothpaste off my Target shopping list.',
                  'Mina, cross toothpaste off the Target list'):
            with self.subTest(q=q):
                self.assertEqual(prepare_remove_item_action(q,self.hub)['item_id'],'target2')

    def test_whitespace_casing(self):
        q='Mina remove  ToothPaste   from my Target list.'
        self.assertEqual(prepare_remove_item_action(q,self.hub)['expected_name'],'toothpaste')

    def test_store_specific(self):
        q="Mina, remove toothpaste from my Trader Joe’s shopping list."
        self.assertEqual(prepare_remove_item_action(q,self.hub)['item_id'],'tj1')

    def test_single_item_with_and_in_name(self):
        q='Mina remove mac and cheese from Target shopping list.'
        self.assertEqual(prepare_remove_item_action(q,self.hub)['item_id'],'target3')

    def test_no_match_blocks(self):
        with self.assertRaisesRegex(ListRemovalError,'not found'):
            prepare_remove_item_action('Mina remove pasta from my Target list',self.hub)

    def test_duplicate_item_name_blocks(self):
        self.hub['stores']['target'].append({'id':'target4','name':'TOOTHPASTE','done':False})
        with self.assertRaisesRegex(ListRemovalError,'more than one'):
            prepare_remove_item_action(self.command,self.hub)

    def test_missing_store_blocks(self):
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action('Mina, remove toothpaste from my shopping list.',self.hub)

    def test_two_stores_blocks(self):
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action('Mina remove toothpaste from Target list and Trader Joe\'s list.',self.hub)

    def test_two_items_blocks(self):
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action('Mina remove toothpaste and dish soap from Target list',self.hub)

    def test_compound_email_blocks(self):
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action('Mina remove toothpaste from Target list and email my husband.',self.hub)

    def test_wrong_store_does_not_delete(self):
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action('Mina remove milk from Target list',self.hub)

    def test_other_write_unchanged(self):
        self.assertFalse(is_list_removal_request('Mina, remove my calendar event.'))
        self.assertFalse(is_list_removal_request('Mina send an email'))
        self.assertFalse(is_list_removal_request('Mina add milk to Costco shopping list.'))

    def test_old_external_write_fallback_avoided(self):
        self.assertTrue(is_list_removal_request(self.command))

    def test_inaccessible_hub_blocks(self):
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action(self.command,None)

    def test_no_valid_id_blocks(self):
        self.hub['stores']['target'][1]['id']=''
        with self.assertRaises(ListRemovalError):
            prepare_remove_item_action(self.command,self.hub)

    def test_unchanged_id_but_name_changed_blocks_commit(self):
        action=prepare_remove_item_action(self.command,self.hub)
        self.hub['stores']['target'][1]['name']='white toothpaste'
        before=deepcopy(self.hub)
        with self.assertRaises(ListRemovalError):
            commit_remove_item_action(self.hub,action)
        self.assertEqual(self.hub,before)

    def test_removed_between_preview_and_confirmation_blocks(self):
        action=prepare_remove_item_action(self.command,self.hub)
        self.hub['stores']['target'].pop(1)
        before=deepcopy(self.hub)
        with self.assertRaises(ListRemovalError):
            commit_remove_item_action(self.hub,action)
        self.assertEqual(self.hub,before)

    def test_duplicate_added_after_preview_blocks(self):
        action=prepare_remove_item_action(self.command,self.hub)
        self.hub['stores']['target'].append({'id':'target5','name':'toothpaste','done':False})
        before=deepcopy(self.hub)
        with self.assertRaises(ListRemovalError):
            commit_remove_item_action(self.hub,action)
        self.assertEqual(self.hub,before)

    def test_no_double_confirm_duplicate(self):
        action=prepare_remove_item_action(self.command,self.hub)
        result=commit_remove_item_action(self.hub,action)
        with self.assertRaises(ListRemovalError):
            commit_remove_item_action(result,action)

    def test_wrong_action_type_blocks(self):
        with self.assertRaises(ListRemovalError):
            commit_remove_item_action(self.hub,{'kind':'list','store':'target','item_id':'target2','expected_name':'toothpaste'})

    def test_store_key_mismatch_and_fake_id_blocks(self):
        action=prepare_remove_item_action(self.command,self.hub)
        action['store']='costco'
        with self.assertRaises(ListRemovalError):
            commit_remove_item_action(self.hub,action)


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code=Path(__file__).with_name('streamlit_app.py').read_text(encoding='utf-8')
        cls.tree=ast.parse(cls.code)

    def test_approval_dispatch_shared_by_button_and_voice(self):
        self.assertEqual(self.code.count('updated = _apply_hub_action('),2)
        self.assertIn("if action.get('kind') == 'remove_item':", self.code)
        self.assertIn('return commit_remove_item_action(current, action)',self.code)

    def test_route_before_generic_external_write(self):
        self.assertLess(self.code.index('elif removal_detected:'),self.code.index("elif auto_intent.kind == 'external_write':"))
        self.assertIn('removal_detected = is_list_removal_request(prompt)',self.code)

    def test_preview_only_proposes(self):
        piece=self.code.split('elif removal_detected:')[1].split('elif spoken_visit_status')[0]
        self.assertIn('pending_hub_action = removal_action',piece)
        self.assertIn('preview_remove_item_action(removal_action)',piece)
        self.assertNotIn('_store_local_hub(',piece)

    def test_confirmation_button_and_cancel(self):
        self.assertIn('Confirm item removal',self.code)
        self.assertIn("if st.button('Cancel change'",self.code)
        self.assertIn('message[\'pending_hub_action\'] = None',self.code)

    def test_confirmation_message_renders_at_runtime(self):
        fn = next(x for x in self.tree.body if isinstance(x, ast.FunctionDef)
                  and x.name == '_approval_message')
        env={'STORE_LABELS':{'target':'Target','costco':'Costco','trader_joes':"Trader Joe's"}}
        compiled=compile(ast.Module(body=[fn],type_ignores=[]),'<approval-message>','exec')
        exec(compiled,env)
        text=env['_approval_message']({'kind':'remove_item','store':'target',
                                       'expected_name':'toothpaste'})
        self.assertIn('Removed toothpaste',text)
        self.assertIn('Target',text)
        self.assertIn('after your confirmation',text)

    def test_clarification_on_failed_lookup(self):
        piece=self.code.split('elif removal_detected:')[1].split('elif spoken_visit_status')[0]
        self.assertIn("status='needs_clarification'",piece)
        self.assertIn('Nothing was removed',piece)


if __name__=='__main__':
    unittest.main()
