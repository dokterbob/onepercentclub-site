import logging
from apps.fund.models import Donation

logger = logging.getLogger(__name__)

from django.contrib import admin

from sorl.thumbnail.admin import AdminImageMixin
from sorl.thumbnail.shortcuts import get_thumbnail

from .models import (Project, IdeaPhase, FundPhase, ActPhase, ResultsPhase, BudgetLine,Testimonial,
                    PartnerOrganization, ProjectPitch)


class ProjectPitchAdmin(admin.ModelAdmin):

    model = ProjectPitch
    list_filter = ('status', )
    list_display = ('title', 'status', 'created')

admin.site.register(ProjectPitch, ProjectPitchAdmin)


class PhaseInlineBase(admin.StackedInline):
    max_num = 1
    extra = 0


class IdeaPhaseInline(PhaseInlineBase):
    model = IdeaPhase
    can_delete = False


class FundPhaseInline(PhaseInlineBase):
    model = FundPhase


class ActPhaseInline(PhaseInlineBase):
    model = ActPhase


class ResultsPhaseInline(PhaseInlineBase):
    model = ResultsPhase


class BudgetInline(admin.TabularInline):
    model = BudgetLine
    extra = 0


class ProjectAdmin(AdminImageMixin, admin.ModelAdmin):

    date_hierarchy = 'created'

    prepopulated_fields = {"slug": ("title",)}

    list_filter = ('phase', )
    list_display = ('title', 'owner')

    inlines = [BudgetInline, IdeaPhaseInline, FundPhaseInline, ActPhaseInline, ResultsPhaseInline]

    search_fields = ('title', 'owner__first_name', 'owner__last_name')

    raw_id_fields = ('owner', )

    def thumbnail(self, instance):
        """
        Generate a nice little thumbnail for our project.
        Source: https://github.com/sorl/sorl-thumbnail/blob/master/sorl/thumbnail/admin/current.py#L19
        """
        value = '<div style="height:80px;width:80px">%s</div>'

        if instance.image:
            try:
                mini = get_thumbnail(
                    instance.image, '80x80', upscale=False, crop='center'
                )
            except Exception:
                logger.exception(
                    "An error occurred while scaling an image in the admin."
                )
                return value % ''
            else:
                return value % (u'<img width="%s" height="%s" src="%s">' % (mini.width, mini.height, mini.url))
        else:
            return value % ''
    thumbnail.allow_tags = True


admin.site.register(Project, ProjectAdmin)
admin.site.register(Testimonial)


class PartnerOrganizationAdmin(AdminImageMixin, admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

admin.site.register(PartnerOrganization, PartnerOrganizationAdmin)


