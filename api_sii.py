import os
import sys
import glob
import subprocess
import time
from datetime import datetime
from fastapi import FastAPI
from pydantic import BaseModel
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

app = FastAPI()


# -------------------------------------------------------
# Verificar instalación de Playwright
# -------------------------------------------------------
def ensure_playwright_browsers():
    chromium_path = os.path.expanduser("~\\AppData\\Local\\ms-playwright\\chromium-*")
    matches = glob.glob(chromium_path)

    if matches:
        chrome_exe = os.path.join(matches[0], "chrome-win", "chrome.exe")
        if os.path.exists(chrome_exe):
            return

    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


ensure_playwright_browsers()


# -------------------------------------------------------
# MODELO DE ENTRADA PARA POSTMAN
# -------------------------------------------------------
class RutRequest(BaseModel):
    rut: str


# -------------------------------------------------------
# FUNCIÓN PRINCIPAL PARA CONSULTAR EL SII
# -------------------------------------------------------
def consultar_sii(RutPersona):

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--window-position=-3000,-3000"
            ]
        )

        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www2.sii.cl/stc/noauthz")

        # ==== Ocultar ventana ====
        session = context.new_cdp_session(page)
        info = session.send("Browser.getWindowForTarget")
        window_id = info["windowId"]
        session.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "left": -3000,
                    "top": -3000,
                    "width": 1200,
                    "height": 800
                }
            }
        )

        # ==============================
        # INGRESAR RUT
        # ==============================
        try:
            page.wait_for_selector("input.rut-form", timeout=20000)
            page.click("input.rut-form")
            page.fill("input.rut-form", RutPersona)
        except:
            browser.close()
            return {"error": "No se encontró el campo RUT"}

        # ==============================
        # CLIC EN CONSULTAR
        # ==============================
        try:
            page.wait_for_selector('input[value="Consultar Situación Tributaria"]', timeout=20000)
            page.click('input[value="Consultar Situación Tributaria"]')
        except:
            browser.close()
            return {"error": "No se encontró el botón Consultar"}

        # ==============================
        # VALIDAR MENSAJE DE ERROR
        # ==============================
        try:
            page.wait_for_selector("div.input-errors", timeout=5000)
            msg = page.inner_text("div.input-errors")
            if msg.strip() != "":
                browser.close()
                return {"error": msg}
        except PlaywrightTimeoutError:
            pass  # No hay error

        # ==============================
        # OBTENER NOMBRE / RAZÓN SOCIAL
        # ==============================
        try:
            page.wait_for_selector("label.mb-1.font-body", timeout=5000)
            texto = page.inner_text("label.mb-1.font-body").strip()
            nombre = texto.replace("Nombre o Razón Social:", "").strip()
        except:
            nombre = ""

        # ==============================
        # DESPLEGAR TABLA
        # ==============================
        try:
            page.wait_for_selector("button.open-btn", timeout=5000)
            page.click("button.open-btn")
        except:
            pass

        # ==============================
        # EXTRAER TABLA
        # ==============================
        try:
            page.wait_for_selector("table#DataTables_Table_0", timeout=15000)
            tabla = page.evaluate("""
            () => {
                const filas = [];
                const tbody = document.querySelector("#DataTables_Table_0 tbody");
                if (!tbody) return filas;

                for (const tr of tbody.querySelectorAll("tr")) {
                    const celdas = [...tr.querySelectorAll("td")].map(td => td.innerText.trim());
                    filas.push(celdas);
                }
                return filas;
            }
            """)
        except:
            tabla = []

        browser.close()

        # ==============================
        # BUSCAR LA FECHA MÁS RECIENTE
        # ==============================
        fila_mas_reciente = None
        fecha_mas_reciente = None

        for fila in tabla:
            try:
                fecha_dt = datetime.strptime(fila[5], "%d-%m-%Y")
                if fecha_mas_reciente is None or fecha_dt > fecha_mas_reciente:
                    fecha_mas_reciente = fecha_dt
                    fila_mas_reciente = fila
            except:
                continue

        # Respuesta final
        return {
            "rut": RutPersona,
            "nombre": nombre,
            "ultima_fila": fila_mas_reciente,
            "tabla_completa": tabla
        }



# -------------------------------------------------------
# ENDPOINT POST PARA POSTMAN
# -------------------------------------------------------
@app.post("/consultar-rut")
def api_consultar_rut(req: RutRequest):
    return consultar_sii(req.rut)
