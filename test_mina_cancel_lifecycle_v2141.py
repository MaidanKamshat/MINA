"""MINA v2.14.1 cancel phrase and task-lifecycle regression tests. Offline."""
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import unittest
from mina_conversation_state_v214 import create_pending_route,decide_followup,VERSION

NOW=datetime(2026,11,22,15,0,tzinfo=timezone.utc)
REQUEST="Mina, plan Costco and library stops before school pickup on November 23, 2026. I haven't decided what time to leave home"

def pending():
    return create_pending_route(REQUEST,date_anchor=date(2026,11,22),
        plan_date='2026-11-23',requested={'groceries','library','school_pickup'},now=NOW)

class CancelLifecycleTests(unittest.TestCase):
    def test_correct_version(self):
        self.assertEqual(VERSION,'2.14.1')

    def test_verbatim_user_bug_report(self):
        self.assertEqual(decide_followup(pending(),'Cancel that route plan',now=NOW).kind,'cancel')

    def test_common_natural_cancellation_variants(self):
        for utterance in (
            'Cancel route','Cancel that route plan','Cancel my route plan',
            'Cancel the pending route plan','Cancel this trip','Cancel the plan',
            'Never mind','Never mind, cancel the route','Mina, cancel that route plan.',
            'Stop planning this trip','Forget that route','Please cancel this plan',
            'no thanks','Cancel',
        ):
            with self.subTest(utterance=utterance):
                d=decide_followup(pending(),utterance,now=NOW)
                self.assertEqual(d.kind,'cancel')
                self.assertIn('No route was calculated',d.message)

    def test_never_interpret_other_cancellations_as_route_cancel(self):
        for utterance in ('Cancel my dentist appointment',
                          'Cancel the meeting on November 24',
                          'Cancel my Target shopping item',
                          'Cancel that route plan and send an email',
                          'What if I cancel my class?'):
            with self.subTest(utterance=utterance):
                self.assertEqual(decide_followup(pending(),utterance,now=NOW).kind,'new_request')

    def test_after_cancel_short_time_not_resumed(self):
        d=decide_followup(pending(),'Cancel that route plan',now=NOW)
        self.assertEqual(d.kind,'cancel')
        # Streamlit clears mina_pending_route for this event before another turn.
        self.assertEqual(decide_followup(None,'12:30 PM',now=NOW).kind,'none')

    def test_short_answer_and_new_task_still_work(self):
        self.assertEqual(decide_followup(pending(),'12:30 PM',now=NOW).kind,'resume')
        self.assertEqual(decide_followup(pending(),"What's on my Target shopping list?",now=NOW).kind,'new_request')

    def test_app_routes_cancel_before_generic_planning(self):
        app=Path(__file__).with_name('streamlit_app.py').read_text()
        self.assertIn("if conversation.kind in {'cancel', 'reprompt', 'expired'}:",app)
        self.assertIn("if conversation.kind in {'resume', 'cancel', 'expired', 'new_request'}:",app)
        self.assertIn("'status':'cancel'",app)

if __name__ == '__main__': unittest.main()
