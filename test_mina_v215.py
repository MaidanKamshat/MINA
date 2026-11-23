from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date, timedelta
import os,sys,unittest
sys.path.insert(0,str(Path(__file__).parent))
from mina_reminders_v215 import (parse_create, read, add, update, listing, is_read,
    read_query, ReminderError)
from mina_memory_v215 import (append_exchange, recent_turns, search_turns,
    pin_fact, facts, erase_history, erase_all, set_opt_in, load_opt_in, memory_request)
from mina_multiturn_v215 import handle

DAY=date(2026,11,22)
class ReminderTests(unittest.TestCase):
 def test_create_explicit(self):
    p=parse_create('Mina, remind me on November 24, 2026 at 9:00 AM to check MINA QA TEST.',today=DAY,timezone_name='America/New_York')
    self.assertEqual(p['title'],'check MINA QA TEST')
    self.assertEqual(p['due'][:16],'2026-11-24T09:00')
 def test_tomorrow(self):
    p=parse_create('Remind me tomorrow at 8 PM to return library books',today=DAY,timezone_name='America/New_York')
    self.assertEqual(p['due'][:16],'2026-11-23T20:00')
 def test_no_date(self):
    with self.assertRaises(ReminderError):
     parse_create('remind me to buy milk',today=DAY,timezone_name='America/New_York')
 def test_no_am_pm(self):
    with self.assertRaises(ReminderError):
     parse_create('remind me tomorrow at 9 to pay bill',today=DAY,timezone_name='America/New_York')
 def test_non_reminder(self):
    self.assertIsNone(parse_create('create a calendar event tomorrow at 9 AM',today=DAY,timezone_name='America/New_York'))
 def test_create_read_done_delete(self):
    with TemporaryDirectory() as d:
     path=Path(d)/'rem.json'
     a=parse_create('Remind me tomorrow at 9 AM to test',today=DAY,timezone_name='America/New_York')
     self.assertEqual(read(path),[])
     r=add(a,path=path)
     self.assertEqual(len(listing(path=path)),1)
     self.assertFalse(listing(path=path)[0]['done'])
     update(r['id'],'done',path=path)
     self.assertEqual(len(listing(only_open=True,path=path)),0)
     update(r['id'],'delete',path=path)
     self.assertEqual(read(path),[])
 def test_corrupt_store_fails_closed(self):
    with TemporaryDirectory() as d:
     p=Path(d)/'r.json';p.write_text('{"version":1,"reminders":[{"title":"unsafe"}]}')
     with self.assertRaises(ReminderError):read(p)
 def test_read_today(self):
    self.assertTrue(is_read('What reminders do I have saved for today?'))
    self.assertEqual(read_query('Do I have reminders today?',DAY),(DAY,DAY))
 def test_range(self):
    self.assertEqual(read_query('what reminders do I have from November 22, 2026 through November 28, 2026?',DAY),
                     (DAY, date(2026,11,28)))
 def test_no_external(self):
    p=parse_create('remind me tomorrow at 9 AM to buy milk',today=DAY,timezone_name='America/New_York')
    self.assertEqual(set(p),{'title','due'})

class MemoryTests(unittest.TestCase):
 def test_opt_in_default_off(self):
    with TemporaryDirectory() as d:
     p=Path(d)/'consent.json'; self.assertFalse(load_opt_in(p));set_opt_in(True,p);self.assertTrue(load_opt_in(p))
     set_opt_in(False,p);self.assertFalse(load_opt_in(p))
 def test_corrupt_opt_in_fails(self):
    from mina_memory_v215 import MemoryErrorLocal
    with TemporaryDirectory() as d:
     p=Path(d)/'c.json';p.write_text('invalid')
     with self.assertRaises(MemoryErrorLocal):load_opt_in(p)
 def test_archive_and_search(self):
    with TemporaryDirectory() as d:
     p=Path(d)/'db.sqlite3'
     append_exchange('session1','Plan library and Costco','Here is your route',path=p)
     append_exchange('session2','Get my library books','Okay',path=p)
     self.assertEqual(len(recent_turns(path=p)),4)
     self.assertEqual(len(search_turns('LIBRARY',path=p)),2)
 def test_pinned_and_erased(self):
    with TemporaryDirectory() as d:
     p=Path(d)/'db.sqlite3'
     append_exchange('session1','Hello','Hey',path=p)
     pin_fact('Prefers quick voice replies',path=p)
     self.assertEqual(len(facts(path=p)),1)
     erase_history(path=p)
     self.assertEqual(len(recent_turns(path=p)),0)
     self.assertEqual(len(facts(path=p)),1)
     erase_all(path=p)
     self.assertEqual(len(facts(path=p)),0)
 def test_explicit_memory_intent(self):
    self.assertEqual(memory_request('Remember that I like morning appointments'),('pin','I like morning appointments'))
    self.assertEqual(memory_request('What did I tell you about Costco?'),('search','Costco'))
    self.assertIsNone(memory_request('Take me to Costco'))

class MultiTurnTests(unittest.TestCase):
 def test_list_missing_store(self):
    a=handle(None,'Mina, add oatmeal to my shopping list',today=DAY)
    self.assertEqual(a.kind,'ask_store');self.assertEqual(a.pending['item'],'oatmeal')
    b=handle(a.pending,'Target',today=DAY)
    self.assertEqual(b.kind,'list_ready');self.assertEqual(b.action['store'],'target')
 def test_calendar_missing_datetime(self):
    a=handle(None,'Mina, schedule a dentist appointment',today=DAY)
    self.assertEqual(a.kind,'ask_calendar')
    b=handle(a.pending,'November 24, 2026 at 10:00 AM',today=DAY)
    self.assertEqual(b.kind,'calendar_ready');self.assertEqual(b.action['date'],'2026-11-24')
 def test_ambiguous_time_not_assumed(self):
    a=handle(None,'schedule dentist appointment',today=DAY)
    b=handle(a.pending,'Tuesday at 10',today=DAY)
    self.assertEqual(b.kind,'reprompt')
 def test_new_request_supersedes(self):
    a=handle(None,'add milk to my shopping list',today=DAY)
    b=handle(a.pending,"What's on my Target shopping list?",today=DAY)
    self.assertEqual(b.kind,'new_request')
 def test_cancel_no_save(self):
    a=handle(None,'add bananas to my shopping list',today=DAY)
    b=handle(a.pending,'Cancel that',today=DAY)
    self.assertEqual(b.kind,'cancel');self.assertIsNone(b.action)
 def test_invalid_store_not_fabricated(self):
    a=handle(None,'add shampoo to my shopping list',today=DAY)
    b=handle(a.pending,'somewhere',today=DAY)
    self.assertEqual(b.kind,'reprompt')
 def test_unrelated_input_ignored(self):
    self.assertEqual(handle(None,'what is the weather today?',today=DAY).kind,'none')
 def test_calendar_unconfirmed(self):
    a=handle(None,'schedule a dentist appointment',today=DAY)
    b=handle(a.pending,'November 24, 2026 at 10 AM',today=DAY)
    self.assertEqual(set(b.action),{'title','date','time'})

if __name__=='__main__':unittest.main()
