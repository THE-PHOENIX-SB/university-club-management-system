# White-box (unit) tests for app.py - each test targets a specific branch/path in the code.
# Run:  python -m unittest test_whitebox -v
import os, tempfile, unittest
import app


class WhiteBox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        app.DB = self.tmp.name          #temporary database
        app.setup_database()
        self.c = app.app.test_client()

    def tearDown(self):
        os.remove(self.tmp.name)

    # helpers
    def reg(self, name="Asha", email="asha@test.com", pwd="Pass@1234", client=None):
        return (client or self.c).post("/register", data={"name": name, "email": email, "password": pwd})

    def login(self, email="asha@test.com", pwd="Pass@1234", client=None):
        return (client or self.c).post("/login", data={"email": email, "password": pwd})

    def coord(self):
        c = app.app.test_client()
        self.login("coordinator@ucms.com", "Coord@1234", c)
        return c

    # ---- register(): every decision branch ----
    def test_WB01_register_get(self):
        self.assertEqual(self.c.get("/register").status_code, 200)

    def test_WB02_register_name_empty(self):
        self.assertIn(b"Name is required", self.reg(name="").data)

    def test_WB03_register_email_empty(self):
        self.assertIn(b"Email is required", self.reg(email="").data)

    def test_WB04_register_email_no_at(self):
        self.assertIn(b"Invalid email", self.reg(email="asha.test.com").data)

    def test_WB05_register_email_no_dot_in_domain(self):
        self.assertIn(b"Invalid email", self.reg(email="asha@test").data)

    def test_WB06_register_email_ends_with_dot(self):
        self.assertIn(b"Invalid email", self.reg(email="asha@test.").data)

    def test_WB07_register_password_empty(self):
        self.assertIn(b"Password is required", self.reg(pwd="").data)

    def test_WB08_register_password_7_chars(self):
        self.assertIn(b"at least 8", self.reg(pwd="Pass123").data)

    def test_WB09_register_password_8_chars_success(self):
        self.assertIn(b"Registration successful", self.reg(pwd="Pass1234").data)

    def test_WB10_register_duplicate_email(self):
        self.reg()
        self.assertIn(b"already registered", self.reg().data)

    def test_WB11_password_is_hashed_in_db(self):
        self.reg()
        row = app.query("SELECT password FROM users WHERE email=?", ("asha@test.com",), one=True)
        self.assertNotEqual(row["password"], "Pass@1234")

    # ---- login(): every branch ----
    def test_WB12_login_get(self):
        self.assertEqual(self.c.get("/login").status_code, 200)

    def test_WB13_login_empty_fields(self):
        self.assertIn(b"required", self.login("", "").data)

    def test_WB14_login_unknown_email(self):
        self.assertIn(b"Invalid email or password", self.login("none@test.com", "x").data)

    def test_WB15_login_wrong_password(self):
        self.reg()
        self.assertIn(b"Invalid email or password", self.login(pwd="Wrong@123").data)

    def test_WB16_login_student_redirect(self):
        self.reg()
        self.assertTrue(self.login().headers["Location"].endswith("/dashboard"))

    def test_WB17_login_coordinator_redirect(self):
        r = self.login("coordinator@ucms.com", "Coord@1234")
        self.assertTrue(r.headers["Location"].endswith("/coordinator"))

    def test_WB18_logout_clears_session(self):
        self.reg(); self.login()
        self.c.get("/logout")
        self.assertTrue(self.c.get("/dashboard").headers["Location"].endswith("/login"))

    # ---- check_access(): 3 paths ----
    def test_WB19_access_logged_out_redirects(self):
        self.assertTrue(self.c.get("/coordinator").headers["Location"].endswith("/login"))

    def test_WB20_access_wrong_role_403(self):
        self.reg(); self.login()
        self.assertEqual(self.c.get("/coordinator").status_code, 403)

    def test_WB21_access_correct_role_200(self):
        self.reg(); self.login()
        self.assertEqual(self.c.get("/dashboard").status_code, 200)

    # ---- request_membership(): every branch ----
    def test_WB22_request_no_club(self):
        self.reg(); self.login()
        self.assertIn(b"select a club", self.c.post("/request", data={"club_id": ""}).data)

    def test_WB23_request_success_pending(self):
        self.reg(); self.login()
        self.assertIn(b"Pending", self.c.post("/request", data={"club_id": "1"}).data)

    def test_WB24_request_duplicate(self):
        self.reg(); self.login()
        self.c.post("/request", data={"club_id": "1"})
        self.assertIn(b"already requested", self.c.post("/request", data={"club_id": "1"}).data)

    # ---- decide(): every branch ----
    def _pending(self):
        self.reg(); self.login()
        self.c.post("/request", data={"club_id": "1"})

    def test_WB25_decide_approve(self):
        self._pending(); self.coord().post("/decide/1/approve")
        self.assertEqual(app.query("SELECT status FROM membership_requests", one=True)["status"], "Approved")

    def test_WB26_decide_reject(self):
        self._pending(); self.coord().post("/decide/1/reject")
        self.assertEqual(app.query("SELECT status FROM membership_requests", one=True)["status"], "Rejected")

    def test_WB27_decide_already_processed_unchanged(self):
        self._pending(); co = self.coord()
        co.post("/decide/1/approve"); co.post("/decide/1/reject")
        self.assertEqual(app.query("SELECT status FROM membership_requests", one=True)["status"], "Approved")

    def test_WB28_student_cannot_decide(self):
        self._pending()
        self.assertEqual(self.c.post("/decide/1/approve").status_code, 403)


if __name__ == "__main__":
    unittest.main()