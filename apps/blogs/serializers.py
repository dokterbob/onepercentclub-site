from fluent_contents.rendering import render_placeholder
from rest_framework import serializers


from bluebottle.accounts.serializers import UserPreviewSerializer
from bluebottle.bluebottle_drf2.serializers import SorlImageField
from bluebottle.bluebottle_utils.serializers import MetaField


from .models import BlogPost


class BlogPostContentsField(serializers.Field):

    def to_native(self, obj):
        request = self.context.get('request', None)
        contents_html = render_placeholder(request, obj)
        return contents_html


class BlogPostSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='slug')
    body = BlogPostContentsField(source='contents')
    main_image = SorlImageField('main_image', '300x200',)
    author = UserPreviewSerializer()

    meta_data = MetaField(
        description = 'get_meta_description',
        image_source = 'main_image',
        )

    class Meta:
        model = BlogPost
        fields = ('id', 'title', 'body', 'main_image', 'author', 'publication_date', 'allow_comments', 'post_type', 'language', 'meta_data')


class BlogPostPreviewSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='slug')

    class Meta:
        model = BlogPost
        fields = ('id', 'title', 'publication_date')

