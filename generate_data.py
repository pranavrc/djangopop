#!/usr/bin/env python

from django.core.management.base import BaseCommand, CommandError
from optparse import make_option

from django.db import models
from faker import Factory
from random import choice


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--module',
                    dest='module',
                    help='App name.'),
        make_option('--model',
                    dest='model',
                    help='Model name.'),
        make_option('--size',
                    dest='size',
                    help='Number of model instances to generate.')
    )

    def handle(self, *args, **options):
        if not options['module']:
            raise CommandError('You must specify a module name with --module.')
        if not options['model']:
            raise CommandError('You must specify a model name with --model.')
        if not options['size']:
            raise CommandError('You must specify a size with --size.')

        module = options['module']
        model = options['model']

        try:
            size = int(options['size'])

            if size > 1000 or size < 0:
                raise ValueError('Size must be a positive integer ' +
                                 'less than or equal to 1000.')
        except ValueError:
            raise CommandError('Size must be a positive integer ' +
                               'less than or equal to 1000.')

        db_model = models.get_model(module, model)

        if db_model:
            data_generator = DataGenerator(db_model, size)
            data_generator.generate_data()
        else:
            raise CommandError('Model could not be found.')


class DataGenerator(object):
    def __init__(self, model, count):
        self.model = model
        self.count = count
        faker = Factory.create()

        self.type_map = {'BooleanField': faker.boolean,
                         'CharField': faker.name,
                         'EmailField': faker.email,
                         'SlugField': faker.slug,
                         'URLField': faker.url,
                         'DateField': faker.date,
                         'DateTimeField': faker.date_time,
                         'IntegerField': faker.random_number,
                         'BigIntegerField': faker.random_number,
                         'PositiveIntegerField': faker.random_number,
                         'PositiveSmallIntegerField': lambda: faker.random_number() % 32767,
                         'SmallIntegerField': lambda: faker.random_number() % 32767,
                         'NullBooleanField': faker.null_boolean,
                         'TextField': faker.text,
                         'TimeField': faker.time,
                         'ForeignKey': lambda foreign, exclude=None: self.foreign_object_helper(foreign, exclude)}

    def generate_data(self, related=None):
        ''' Recursively generates data for the current model,
            its dependencies and other models related by keys. '''
        fields = [field for field in self.model._meta.fields
                  if not field.null and not field.blank and
                  str(field.default) == 'django.db.models.fields.NOT_PROVIDED']

        for counter in range(self.count):
            model_instance = self.model()

            for field in fields:
                field_name = field.__class__.__name__

                if field.rel:
                    if not field.rel.to._meta.object_name == related and \
                       not field.rel.to.objects.count():
                        data_generator = DataGenerator(field.rel.to, self.count)
                        data_generator.generate_data()
                    value = self.type_map[field_name](field.rel.to)
                else:
                    value = self.type_map[field_name]()

                if field.unique:
                    if field.rel:
                        value = self.type_map[field_name](field.rel.to, value.pk)
                        if not value:
                            return
                        try:
                            self.model.objects.get(**{field.attname: value})
                            return
                        except self.model.DoesNotExist:
                            pass
                    else:
                        while True:
                            try:
                                self.model.objects.get(**{field.attname: value})
                                value = self.type_map[field_name]()
                                continue
                            except self.model.DoesNotExist:
                                break

                if field.choices:
                    value = choice(field.choices)[0]
                elif field.max_length:
                    value = value[0:field.max_length]

                setattr(model_instance, field.name, value)

            model_instance.save()

            self.generate_related_objects(model_instance)

    def generate_related_objects(self, model_instance):
        ''' Helper function to generate data for dependent models.'''
        related_objects = model_instance.__class__._meta.get_all_related_objects()

        for related_object in related_objects:
            if related_object.model._meta.object_name not in \
               [field.rel.to._meta.object_name for field in
                    model_instance.__class__._meta.fields if field.rel]:
                data_generator = DataGenerator(related_object.model, self.count)
                data_generator.generate_data(related=model_instance.__class__.__name__)

    def foreign_object_helper(self, foreign, exclude=None):
        results = foreign.objects.exclude(pk=exclude)

        if results.count():
            return results.order_by('?')[0]
        else:
            return []
