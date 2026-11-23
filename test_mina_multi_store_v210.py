"""Offline safety and correctness regression tests for MINA v2.10."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import ast
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mina_multi_store_v210 import (
    MultiStoreParseError, STORE_LABELS, is_multi_store_add_request,
    parse_multi_store_add, prepare_multi_store_action, preview_multi_store_action,
    commit_multi_store_action, remove_one_local_item,
)

REQUEST = "Mina, add strawberries and yogurt to my Target shopping list, and rice and olive oil to my Trader Joe's shopping list."


def fake_add(hub, store, item):
    result = deepcopy(hub)
    result['stores'][store].append({'id':f'id{sum(map(len,result["stores"].values()))+1}',
                                    'name':item, 'done':False})
    return result


class MultiStoreParserTests(unittest.TestCase):
    def test_exact_spoken_scenario(self):
        self.assertEqual(parse_multi_store_add(REQUEST), {
            'target':['strawberries','yogurt'],
            'trader_joes':['rice','olive oil']})

    def test_curly_apostrophe(self):
        self.assertEqual(parse_multi_store_add(REQUEST.replace("Joe's", "Joe’s"))['trader_joes'], ['rice','olive oil'])

    def test_no_apostrophe_in_transcript(self):
        self.assertEqual(parse_multi_store_add(REQUEST.replace("Joe's", 'Trader Joes').replace('Trader Trader', 'Trader'))['trader_joes'], ['rice','olive oil'])

    def test_casing_is_irrelevant(self):
        self.assertEqual([x.lower() for x in parse_multi_store_add(REQUEST.upper())['target']], ['strawberries','yogurt'])

    def test_three_stores(self):
        q = "Mina, add cheese to Costco shopping list, and oranges to Target shopping list, and dumplings to Trader Joe's shopping list."
        self.assertEqual(parse_multi_store_add(q), {'costco':['cheese'],'target':['oranges'],'trader_joes':['dumplings']})

    def test_single_store_falls_through_to_legacy(self):
        q = 'Mina, add eggs, bananas, and paper towels to my Costco shopping list.'
        self.assertFalse(is_multi_store_add_request(q))
        self.assertIsNone(parse_multi_store_add(q))

    def test_two_store_names_without_complete_destination_blocks(self):
        with self.assertRaises(MultiStoreParseError):
            parse_multi_store_add('Mina, add apples to Target and milk to Trader Joe\'s shopping list.')

    def test_extra_email_instruction_blocks(self):
        with self.assertRaises(MultiStoreParseError):
            parse_multi_store_add(REQUEST + ' And email my husband.')

    def test_duplicate_store_clause_blocks(self):
        with self.assertRaises(MultiStoreParseError):
            parse_multi_store_add('Mina, add apples to Target list and milk to Costco list and mangoes to Target list.')

    def test_ambiguous_extra_name_blocks(self):
        with self.assertRaises(MultiStoreParseError):
            parse_multi_store_add('Mina, add apples to Target list and milk to Costco list from Trader Joe\'s.')

    def test_no_list_title_inside_an_item(self):
        parsed = parse_multi_store_add(REQUEST)
        for items in parsed.values():
            for item in items:
                self.assertNotIn('list', item)
                self.assertNotIn('Target', item)

    def test_strips_connectors(self):
        parsed = parse_multi_store_add('Mina, please add tea, and biscuits to my Target list, and bananas to my Costco list.')
        self.assertEqual(parsed, {'target':['tea','biscuits'], 'costco':['bananas']})

    def test_prefix_must_be_add_instruction(self):
        with self.assertRaises(MultiStoreParseError):
            parse_multi_store_add('Mina, remove apples from Target list and add rice to Costco list.')

    def test_vague_multi_store_no_auto_routing(self):
        q = 'Add milk to Target, and eggs to Costco'
        self.assertTrue(is_multi_store_add_request(q))
        with self.assertRaises(MultiStoreParseError):parse_multi_store_add(q)

    def test_action_is_explicitly_pending(self):
        self.assertEqual(prepare_multi_store_action(REQUEST)['kind'],'multi_list')
        self.assertIn('not saved yet', preview_multi_store_action(prepare_multi_store_action(REQUEST)).lower())


class MultiStoreCommitTests(unittest.TestCase):
    def setUp(self):
        self.hub = {'stores': {'target': [], 'costco': [], 'trader_joes': [
            {'id':'orig1','name':'spinach pasta','done':False},
            {'id':'orig2','name':'lavender soap','done':False},
        ]}, 'preferences':{'test':'retained'}}

    def test_transaction_fills_both_correctly(self):
        action = prepare_multi_store_action(REQUEST)
        result = commit_multi_store_action(self.hub,action,fake_add)
        self.assertEqual([it['name'] for it in result['stores']['target']], ['strawberries','yogurt'])
        self.assertEqual([it['name'] for it in result['stores']['trader_joes']], ['spinach pasta','lavender soap','rice','olive oil'])
        self.assertEqual(result['stores']['costco'], [])
        self.assertEqual(self.hub['stores']['target'], [])
        self.assertEqual(len(self.hub['stores']['trader_joes']), 2)

    def test_atomicity_on_failure(self):
        original = deepcopy(self.hub)
        def fail_on_rice(hub,store,item):
            if item=='rice': raise ValueError('simulated failure')
            return fake_add(hub,store,item)
        with self.assertRaises(ValueError):
            commit_multi_store_action(self.hub,prepare_multi_store_action(REQUEST),fail_on_rice)
        self.assertEqual(self.hub, original)

    def test_invalid_store_blocks(self):
        with self.assertRaises(MultiStoreParseError):
            commit_multi_store_action(self.hub,{'kind':'multi_list','stores':{'target':['tea'],'unknown':['milk']}},fake_add)

    def test_no_single_store_abuse(self):
        with self.assertRaises(MultiStoreParseError):
            commit_multi_store_action(self.hub,{'kind':'multi_list','stores':{'target':['tea']}},fake_add)

    def test_correct_store_removal_only(self):
        updated = remove_one_local_item(self.hub,'trader_joes','orig2')
        self.assertEqual([x['name'] for x in updated['stores']['trader_joes']], ['spinach pasta'])
        self.assertEqual(len(self.hub['stores']['trader_joes']),2)

    def test_wrong_item_id_blocks(self):
        with self.assertRaises(MultiStoreParseError):
            remove_one_local_item(self.hub,'trader_joes','not-there')


class UIWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = Path(__file__).with_name('streamlit_app.py').read_text(encoding='utf-8')
        cls.ast = ast.parse(cls.code)

    def test_both_confirmation_paths_use_atomic_handler(self):
        # Must be used by button and voice/text confirmations, not only one path.
        self.assertEqual(self.code.count('updated = _apply_hub_action('),2)

    def test_guard_precedes_single_store_legacy_route(self):
        self.assertIn('elif multi_store_detected:',self.code)
        self.assertLess(self.code.index('elif multi_store_detected:'),self.code.index("elif auto_intent.kind == 'local_list_proposal':"))

    def test_preview_assigns_pending_action(self):
        segment = self.code.split('elif multi_store_detected:')[1].split('elif spoken_visit_status')[0]
        self.assertIn('pending_hub_action = multi_store_action',segment)
        self.assertNotIn('_store_local_hub(',segment)

    def test_typed_or_speech_confirmation_is_required(self):
        self.assertIn('is_explicit_local_confirmation(prompt)',self.code)
        self.assertIn("message['pending_hub_action'] = None",self.code)

    def test_no_longer_claim_read_only_on_confirmed_local_write(self):
        self.assertIn("'local_update_completed'",self.code)
        self.assertIn('Confirmed local update · not an external write',self.code)


if __name__=='__main__':unittest.main()
