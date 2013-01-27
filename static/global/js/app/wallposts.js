App.loadTemplates(['wallposts']);


/*
 Models
 */

App.MediaWallPostPhoto = DS.Model.extend({
    photo: DS.attr('string'),
    thumbnail: DS.attr('string')
});

// This is union of all different wallposts.
App.ProjectWallPost = DS.Model.extend({
    url: 'projects/wallposts',

    // Model fields
    project_slug: DS.attr('string'),
    author: DS.belongsTo('App.Member'),
    title: DS.attr('string'),
    text: DS.attr('string'),
    created: DS.attr('string'),
    timesince: DS.attr('string'),
    video_url: DS.attr('string'),
    video_html: DS.attr('string'),
    photo: DS.attr('string'),
    photos: DS.hasMany('App.MediaWallPostPhoto'),
    reactions: DS.hasMany('App.WallPostReaction')
});


App.ProjectMediaWallPost = App.ProjectWallPost.extend({
    url: 'projects/wallposts/media'
});

App.ProjectTextWallPost = App.ProjectWallPost.extend({
    url: 'projects/wallposts/text'
});


/*
 Controllers
 */

App.ProjectWallPostListController = Em.ArrayController.extend({

    // The list of WallPosts are loaded into the temporary 'wallposts' array in the Route. Once this RecordArray
    // is loaded, it is converted to an Ember array and put into content. This temporary array is required
    // because the RecordArray returned by findQuery can't be manipulated directly. Discussion about this
    // can be found in these two pages:
    // http://stackoverflow.com/questions/11895629/add-delete-items-from-ember-data-backed-arraycontroller
    // https://github.com/emberjs/data/issues/370
    wallpostsLoaded: function(sender, key) {
        if (this.get(key)) {
            this.set('content', this.get('wallposts').toArray());
        } else {
            // Don't show old content when new content is being retrieved.
            this.set('content', null);
        }
    }.observes('wallposts.isLoaded')

});


App.ProjectWallPostFormController = Em.ObjectController.extend({

    content: App.ProjectWallPost.createRecord(),

    addMediaWallPost: function() {
        var transaction = App.store.transaction();
        var mediawallpost = transaction.createRecord(App.ProjectMediaWallPost);
        mediawallpost.set('title', this.get('content.title'));
        mediawallpost.set('text', this.get('content.text'));
        mediawallpost.set('video_url', this.get('content.video_url'));
        mediawallpost.set('photo', this.get('content.photo'));
        mediawallpost.set('project_slug', this.get('currentProject.slug'));
        mediawallpost.set('photo_file', this.get('content.photo_file'));
        var controller = this;
        mediawallpost.on('didCreate', function(record) {
            controller.get('projectWallPostListController.content').unshiftObject(record);
            controller.clearWallPost()
        });
        mediawallpost.on('becameInvalid', function(record) {
            controller.set('errors', record.get('errors'));
//            TODO: The record needs need to be deleted somehow.
//            record.deleteRecord();
        });
        transaction.commit();
    },

    addTextWallPost: function() {
        var transaction = App.store.transaction();
        var textwallpost = transaction.createRecord(App.ProjectTextWallPost);
        textwallpost.set('text', this.get('content.text'));
        textwallpost.set('project_slug', this.get('currentProject.slug'));
        var controller = this;
        textwallpost.on('didCreate', function(record) {
            controller.get('projectWallPostListController.content').unshiftObject(record);
            controller.clearWallPost()
        });
        textwallpost.on('becameInvalid', function(record) {
            controller.set('content.errors', record.get('errors'));
//            TODO: The record needs need to be deleted somehow.
//            record.deleteRecord();
        });
        transaction.commit();
    },

    clearWallPost: function() {
        this.set('content.title', '');
        this.set('content.text', '');
        this.set('content.video_url', '');
        this.set('content.photo', '');
        this.set('content.photo_file', null);
        this.set('content.errors', null);
    },

    isProjectOwner: function() {
        var user = this.get('currentUser');
        var owner = this.get('currentProject.owner');
        if (user && owner && user.get('username')) {
            return user.get('username') == owner.get('username');
        }
        return false;
    }.property('currentUser', 'currentProject.owner')

});


/*
 Views
 */

App.MediaWallPostFormView = Em.View.extend({
    templateName: 'media_wallpost_form',
    tagName: 'form',

    submit: function(e){
        e.preventDefault();
        this.get('controller').addMediaWallPost();
    },

    didInsertElement: function() {
        this.get('controller').clearWallPost();
    }

});


App.TextWallPostFormView = Em.View.extend({
    templateName: 'text_wallpost_form',
    tagName: 'form',

    submit: function(e){
        e.preventDefault();
        this.get('controller').addTextWallPost();
    },

    didInsertElement: function() {
        this.get('controller').clearWallPost();
    }

});


App.UploadFileView = Ember.TextField.extend({
    type: 'file',
    attributeBindings: ['name', 'accept'],

    contentBinding: 'parentView.content',

    change: function(e) {
        var input = e.target;
        if (input.files && input.files[0]) {
            var reader = new FileReader();
            var view = this;
            reader.onload = function(e) {
                view.get('content').set('photo_preview', e.target.result);
            };
            reader.readAsDataURL(input.files[0]);
            // The File object needs to be set on the Model so that it can be accesses in the DRF2 adapter.
            this.get('content').set('photo_file', input.files[0]);
        }
    }
});


App.ProjectWallPostView = Em.View.extend({
    templateName: 'projectwallpost',

    isAuthor: function() {
        var username = this.get('user.username');
        var authorname = this.get('content.author.username');
        if (username) {
            return (username == authorname);
        }
        return false;
    }.property('user', 'content'),

    // TODO: Delete reactions to WallPost as well?
    deleteWallPost: function() {
        if (confirm("Delete this wallpost?")) {
            var transaction = App.store.transaction();
            var post = this.get('content');
            transaction.add(post);
            post.deleteRecord();
            transaction.commit();
            var self = this;
            this.$().slideUp(500);
        }
    }

});


// Idea of how to have child views with different templates:
// http://stackoverflow.com/questions/10216059/ember-collectionview-with-views-that-have-different-templates
App.ProjectWallPostListView = Em.View.extend({
    templateName: 'projectwallpost_list'
});
