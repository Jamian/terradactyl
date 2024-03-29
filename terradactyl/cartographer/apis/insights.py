import datetime
import logging

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse


from gremlin_python.process.traversal import T

from cartographer.gizmo.models import Workspace
from cartographer.gizmo.models.exceptions import VertexDoesNotExistException


logger = logging.getLogger(__name__)


@login_required
@require_http_methods(['GET'])
def daily_change(request):
    data = {
        'daily_change': {},
        'stats': {}
    }

    workspaces = Workspace.vertices.all()
    for workspace in workspaces:
        has_current_revision = True
        try:
            workspace.get_current_state_revision()
        except VertexDoesNotExistException:
            has_current_revision = False

        state_revisions = workspace.get_state_revisions() if has_current_revision else []
        for state_revision in state_revisions:
            created_date = datetime.datetime.fromtimestamp(state_revision.created_at)
            seconds = int((created_date - datetime.datetime(1970,1,1)).total_seconds())
            month_year = created_date.strftime('%Y-%m')
            if seconds not in data['daily_change']:
                data['daily_change'][seconds] = 1
            else:
                data['daily_change'][seconds] += 1

            # if created_date.year == 2021:
            if month_year not in data['stats']:
                data['stats'][month_year] = 1
            else:
                data['stats'][month_year] += 1

    total_months = len(data['stats'])
    total_applies = sum(data['stats'].values())

    avg_month = total_applies / total_months
    data['stats']['avg_monthly_applies'] = avg_month

    response = JsonResponse(data)
    return response