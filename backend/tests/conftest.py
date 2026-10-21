"""Configuracion del entorno de pruebas: directorio de subidas real, aislado en disco."""

import os
import tempfile

# Debe fijarse antes de importar src.main, porque /uploads se monta durante la importacion
_UPLOAD_TMP = tempfile.mkdtemp(prefix="upa-test-uploads-")
os.environ.setdefault("UPLOAD_DIR", _UPLOAD_TMP)
