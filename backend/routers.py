from fastapi import APIRouter
import backend.controllers as controllers

router = APIRouter()

router.post("/login")(controllers.login)
router.post("/logout")(controllers.logout)
router.get("/session")(controllers.session_status)

router.get("/tickets")(controllers.get_tickets)
router.post("/tickets", status_code=201)(controllers.post_ticket)
router.post("/sync-emails")(controllers.sync_emails)
router.put("/update-reply/{ticket_id}")(controllers.update_reply)
router.post("/send-reply/{ticket_id}")(controllers.send_reply)

router.get("/", include_in_schema=False)(lambda: controllers.spa_fallback(""))
router.get("/{full_path:path}", include_in_schema=False)(controllers.spa_fallback)
